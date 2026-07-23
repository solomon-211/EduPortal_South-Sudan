from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from db_connection import engine
from settings import BACKUP_DIR, BACKUP_RETENTION_DAYS, DATABASE_URL

log = logging.getLogger(__name__)


def run_backup() -> str:
    """Snapshot the configured database into BACKUP_DIR. Returns the backup file path."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if engine.dialect.name == "sqlite":
        dest = BACKUP_DIR / f"eduportal_{stamp}.sqlite3"
        db_path = engine.url.database
        if not db_path or db_path == ":memory:":
            log.warning("Skipping backup — in-memory SQLite database has nothing to persist")
            return ""
        src_conn = sqlite3.connect(db_path)
        dest_conn = sqlite3.connect(str(dest))
        with dest_conn:
            src_conn.backup(dest_conn)
        src_conn.close()
        dest_conn.close()
    else:
        dest = BACKUP_DIR / f"eduportal_{stamp}.sql"
        parsed = urlparse(DATABASE_URL.replace("mysql+pymysql", "mysql"))
        host = parsed.hostname or "localhost"
        # mysqldump fails to resolve the literal string "localhost" on some
        # Windows setups (falls back to a named pipe / DNS quirk) — 127.0.0.1
        # always works for a local server.
        if host == "localhost":
            host = "127.0.0.1"
        cmd = [
            "mysqldump",
            f"--host={host}",
            f"--port={parsed.port or 3306}",
            f"--user={parsed.username or 'root'}",
            parsed.path.lstrip("/") or "eduportal",
        ]
        env = {**os.environ, "MYSQL_PWD": parsed.password or ""}
        with open(dest, "w", encoding="utf-8") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env, text=True)
        if result.returncode != 0:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"mysqldump failed: {result.stderr}")

    log.info("Database backup written to %s", dest)
    _prune_old_backups()
    return str(dest)


def _prune_old_backups() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=BACKUP_RETENTION_DAYS)
    for f in BACKUP_DIR.glob("eduportal_*"):
        if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) < cutoff:
            f.unlink(missing_ok=True)


def _has_mysqldump() -> bool:
    return shutil.which("mysqldump") is not None
