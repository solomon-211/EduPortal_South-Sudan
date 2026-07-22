from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from db_queries import query_all
from notify_email import send_email
from notify_store import already_notified, create_notification

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

DEADLINE_MILESTONES = (3, 1)  # days before a scholarship deadline to warn applicants


def remind_upcoming_deadlines() -> int:
    """Notify applicants once per milestone as their scholarship deadline approaches."""
    sent = 0
    for days_out in DEADLINE_MILESTONES:
        target_date = (datetime.now(timezone.utc) + timedelta(days=days_out)).date().isoformat()
        rows = query_all(
            """SELECT a.user_id, s.id AS scholarship_id, s.title, s.deadline,
                      u.email, u.name, u.notify_email
               FROM applications a
               JOIN scholarships s ON s.id = a.scholarship_id
               JOIN users u ON u.id = a.user_id
               WHERE s.approved=1 AND date(s.deadline) = date(?)
                 AND a.status NOT IN ('successful','unsuccessful')""",
            (target_date,),
        )
        ntype = f"deadline_{days_out}d"
        for row in rows:
            if already_notified(row["user_id"], ntype, "scholarship", row["scholarship_id"]):
                continue
            day_word = "day" if days_out == 1 else "days"
            title = f"Deadline in {days_out} {day_word}: {row['title']}"
            create_notification(
                row["user_id"], ntype, title, f"Closes {row['deadline']}",
                ref_type="scholarship", ref_id=row["scholarship_id"],
            )
            if row.get("email") and row.get("notify_email"):
                send_email(
                    row["email"],
                    f"EduPortal — {title}",
                    f"Dear {row['name']},\n\nYour application for \"{row['title']}\" closes on "
                    f"{row['deadline']}.\n\nLog in to EduPortal South Sudan to review your application.\n\n"
                    "EduPortal South Sudan",
                )
            sent += 1
    return sent


def _run_safely(fn) -> None:
    try:
        fn()
    except Exception:
        log.exception("Scheduled job %s failed", getattr(fn, "__name__", fn))


def start(app) -> BackgroundScheduler:
    """app is the Flask app — jobs run on a background thread with no request,
    so db.queries (which reads Flask's g) needs an app context pushed manually."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    def _job():
        with app.app_context():
            _run_safely(remind_upcoming_deadlines)

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _job, "interval", hours=6, id="deadline_reminders",
        next_run_time=datetime.now(),  # also run once at startup
    )
    _scheduler.start()
    log.info("Background scheduler started")
    return _scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
