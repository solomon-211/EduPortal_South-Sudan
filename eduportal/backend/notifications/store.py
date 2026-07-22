from __future__ import annotations

import queue
import threading

from db.queries import execute, query_one

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
        from notifications.push import send_push_to_user
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
