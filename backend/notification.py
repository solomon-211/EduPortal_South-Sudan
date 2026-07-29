"""Everything notification: email, SMS, web push, and the persisted/live feed.

Was four files (notify_email.py, notify_sms.py, notify_push.py,
notify_store.py) that split one concept — telling a user something happened
— across separate delivery channels. Merged into one module; each channel
still gets its own section below.
"""
from __future__ import annotations

import json
import logging
import queue
import smtplib
import threading
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pywebpush import WebPushException, webpush

from database import execute, query_all, query_one
from settings import (
    AT_API_KEY,
    AT_SENDER_ID,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASS,
    SMTP_PORT,
    SMTP_USER,
    VAPID_CLAIMS_SUB,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
)

log = logging.getLogger(__name__)


# ── Email ───────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str, html: str | None = None) -> bool:
    if not SMTP_HOST or not SMTP_USER:
        return False
    try:
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html, "html"))
        else:
            msg = MIMEText(body, "plain")  # type: ignore[assignment]
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception as exc:
        log.warning("Email send to %s failed: %s", to, exc)
        return False


def send_verification_email(to: str, name: str, verify_url: str) -> bool:
    subject = "Welcome to EduPortal South Sudan — confirm your account"
    plain = (
        f"Hello {name},\n\n"
        f"Welcome to EduPortal South Sudan!\n\n"
        f"Click the link below to confirm and activate your new account:\n{verify_url}\n\n"
        f"This link expires in 24 hours. If you did not create an account, ignore this email.\n\n"
        f"EduPortal South Sudan"
    )
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:24px;color:#1a1a1a">
  <h2 style="color:#233D4D">Welcome to EduPortal South Sudan!</h2>
  <p>Hello <strong>{name}</strong>,</p>
  <p>Click the button below to confirm and activate your new account.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{verify_url}"
       style="background:#FE7F2D;color:#fff;padding:12px 28px;border-radius:8px;
              text-decoration:none;font-weight:bold;display:inline-block">
      Confirm My Account
    </a>
  </p>
  <p style="font-size:13px;color:#555">
    Or copy this link into your browser:<br>
    <a href="{verify_url}" style="color:#233D4D">{verify_url}</a>
  </p>
  <p style="font-size:12px;color:#888">This link expires in 24 hours.<br>
  If you did not create an account, you can safely ignore this email.</p>
  <hr style="border:none;border-top:1px solid #eee;margin-top:32px">
  <p style="font-size:11px;color:#aaa;text-align:center">EduPortal South Sudan</p>
</body>
</html>"""
    return send_email(to, subject, plain, html)


# ── SMS (Africa's Talking) ──────────────────────────────────────────────

def send_sms(phone: str, message: str) -> bool:
    if not AT_API_KEY:
        return False
    try:
        payload = urllib.parse.urlencode({
            "username": "sandbox" if "sandbox" in AT_API_KEY.lower() else "eduportal",
            "to": phone,
            "message": message,
            "from": AT_SENDER_ID,
        }).encode()
        req = urllib.request.Request(
            "https://api.africastalking.com/version1/messaging",
            data=payload,
            headers={"apiKey": AT_API_KEY, "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
            return result.get("SMSMessageData", {}).get("Recipients", [{}])[0].get("status") == "Success"
    except Exception as exc:
        log.warning("SMS send to %s failed: %s", phone, exc)
        return False


# ── Web Push ────────────────────────────────────────────────────────────

def push_is_configured() -> bool:
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def send_push_to_user(user_id: int, title: str, body: str = "") -> int:
    """Push to every browser this user has subscribed on. Returns count sent."""
    if not push_is_configured():
        return 0
    subs = query_all("SELECT id,endpoint,p256dh,auth FROM push_subscriptions WHERE user_id=?", (user_id,))
    sent = 0
    for sub in subs:
        ok = _send_push_one(sub, title, body)
        if ok:
            sent += 1
        elif ok is False:
            # Endpoint is gone (browser unsubscribed, profile reset, etc.) — stop
            # retrying it instead of failing silently on every future notification.
            execute("DELETE FROM push_subscriptions WHERE id=?", (sub["id"],))
    return sent


def _send_push_one(sub: dict, title: str, body: str) -> bool | None:
    try:
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIMS_SUB},
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return False
        log.warning("Web push failed: %s", exc)
        return None


# ── Persisted notifications + live feed (SSE) ──────────────────────────
# In-process pub/sub: fine behind a single worker, would need a shared
# broker (e.g. Redis) for the SSE fan-out to reach every connection if
# this ever runs behind multiple Gunicorn workers.

_subscribers: dict[int, list[queue.Queue]] = {}
_lock = threading.Lock()


def create_notification(
    user_id: int, ntype: str, title: str, body: str = "",
    ref_type: str | None = None, ref_id: int | None = None,
) -> int:
    """Persist a notification, push it over SSE to open tabs, and Web Push to subscribed browsers."""
    notif_id = execute(
        "INSERT INTO notifications (user_id,type,title,body,ref_type,ref_id) VALUES (?,?,?,?,?,?)",
        (user_id, ntype, title, body, ref_type, ref_id),
    )
    publish(user_id, {"id": notif_id, "type": ntype, "title": title, "body": body, "read": False})
    try:
        send_push_to_user(user_id, title, body)
    except Exception:
        pass  # push is best-effort — a provider hiccup should never break the caller
    return notif_id


def already_notified(user_id: int, ntype: str, ref_type: str, ref_id: int) -> bool:
    row = query_one(
        "SELECT id FROM notifications WHERE user_id=? AND type=? AND ref_type=? AND ref_id=?",
        (user_id, ntype, ref_type, ref_id),
    )
    return row is not None


def subscribe(user_id: int) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=50)
    with _lock:
        _subscribers.setdefault(user_id, []).append(q)
    return q


def unsubscribe(user_id: int, q: queue.Queue) -> None:
    with _lock:
        subs = _subscribers.get(user_id)
        if not subs:
            return
        if q in subs:
            subs.remove(q)
        if not subs:
            _subscribers.pop(user_id, None)


def publish(user_id: int, payload: dict) -> None:
    with _lock:
        subs = list(_subscribers.get(user_id, []))
    for q in subs:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass
