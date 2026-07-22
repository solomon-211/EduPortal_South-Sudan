from __future__ import annotations

import json
import logging

from pywebpush import WebPushException, webpush

from config.settings import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS_SUB
from db.queries import execute, query_all

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def send_push_to_user(user_id: int, title: str, body: str = "") -> int:
    """Push to every browser this user has subscribed on. Returns count sent."""
    if not is_configured():
        return 0
    subs = query_all("SELECT id,endpoint,p256dh,auth FROM push_subscriptions WHERE user_id=?", (user_id,))
    sent = 0
    for sub in subs:
        ok = _send_one(sub, title, body)
        if ok:
            sent += 1
        elif ok is False:
            # Endpoint is gone (browser unsubscribed, profile reset, etc.) — stop
            # retrying it instead of failing silently on every future notification.
            execute("DELETE FROM push_subscriptions WHERE id=?", (sub["id"],))
    return sent


def _send_one(sub: dict, title: str, body: str) -> bool | None:
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
