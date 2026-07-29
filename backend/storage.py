"""File storage — auto-selects S3 or local disk based on env vars.

Was three files (storage.py, storage_local.py, storage_s3.py); merged since
each backend is only a `save`/`public_url` pair and the split added more
navigation than it saved.

Usage (anywhere in the app):
    from storage import save_file, public_url

    stored_key = save_file(dest_dir, filename, file_stream)
    url        = public_url(stored_key)

S3-compatible backend (AWS S3 or Supabase Storage) env vars:
    S3_BUCKET          — bucket name
    S3_REGION          — e.g. us-east-1  (or your Supabase region)
    S3_ACCESS_KEY      — AWS access key ID  /  Supabase service-role key
    S3_SECRET_KEY      — AWS secret access key  /  Supabase secret
    S3_ENDPOINT_URL    — leave blank for AWS; set to Supabase Storage URL for Supabase
                         e.g. https://<project>.supabase.co/storage/v1/s3
    S3_PUBLIC_BASE_URL — optional, base URL for public file access (auto-derived if blank)

Local disk (default / fallback) needs no configuration — files are written
under the app's assets directory and served directly by Flask.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError  # noqa: F401 — re-exported for callers that catch it
    _boto3_available = True
except ImportError:
    _boto3_available = False
    # Give _save_s3's except clause real classes to reference even when boto3
    # isn't installed — _get_s3_client() raises its own RuntimeError first in
    # that case, so these never actually match anything.
    class BotoCoreError(Exception): ...
    class ClientError(Exception): ...

_USE_S3 = bool(os.environ.get("S3_BUCKET") and os.environ.get("S3_ACCESS_KEY"))

_S3_BUCKET       = os.environ.get("S3_BUCKET", "")
_S3_REGION       = os.environ.get("S3_REGION", "us-east-1")
_S3_ACCESS_KEY   = os.environ.get("S3_ACCESS_KEY", "")
_S3_SECRET_KEY   = os.environ.get("S3_SECRET_KEY", "")
_S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")   # blank = AWS
_S3_PUBLIC_BASE  = os.environ.get("S3_PUBLIC_BASE_URL", "")

_s3_client = None


def using_s3() -> bool:
    return _USE_S3


def save_file(dest_dir: Path, filename: str, stream) -> str:
    """Persist *stream* and return the stored key / relative path."""
    return _save_s3(dest_dir, filename, stream) if _USE_S3 else _save_local(dest_dir, filename, stream)


def public_url(stored_key: str) -> str:
    """Resolve a stored key to a publicly accessible URL."""
    return _public_url_s3(stored_key) if _USE_S3 else _public_url_local(stored_key)


# ── Local disk ──────────────────────────────────────────────────────────

def _save_local(dest_dir: Path, filename: str, stream) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename).write_bytes(stream.read())
    return filename  # the caller builds the URL from the filename


def _public_url_local(url_path: str) -> str:
    return url_path  # served directly by Flask, no transformation needed


# ── S3-compatible ───────────────────────────────────────────────────────

def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        if not _boto3_available:
            raise RuntimeError("boto3 is not installed. Run: pip install boto3")
        kwargs: dict = dict(
            region_name=_S3_REGION,
            aws_access_key_id=_S3_ACCESS_KEY,
            aws_secret_access_key=_S3_SECRET_KEY,
        )
        if _S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = _S3_ENDPOINT_URL
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def _save_s3(dest_dir: Path, filename: str, stream) -> str:
    """Upload *stream* to S3 at <bucket>/<dest_dir.name>/<filename>.
    Returns the S3 object key (used as the stored path)."""
    key = f"{dest_dir.name}/{filename}"
    try:
        _get_s3_client().upload_fileobj(
            stream,
            _S3_BUCKET,
            key,
            ExtraArgs={"ContentType": _guess_content_type(filename)},
        )
    except (BotoCoreError, ClientError) as exc:
        # Every upload route's caller has no S3-specific handling of its own —
        # they all rely on app.py's global 500 handler, which logs the full
        # exception. Re-raising with the original cause attached keeps that
        # log entry readable instead of a bare botocore stack trace.
        raise RuntimeError(f"S3 upload failed for {key}: {exc}") from exc
    return key


def _public_url_s3(key: str) -> str:
    if _S3_PUBLIC_BASE:
        return f"{_S3_PUBLIC_BASE.rstrip('/')}/{key}"
    if _S3_ENDPOINT_URL:
        # Supabase pattern: <endpoint>/object/public/<bucket>/<key>
        base = _S3_ENDPOINT_URL.replace("/storage/v1/s3", "/storage/v1")
        return f"{base}/object/public/{_S3_BUCKET}/{key}"
    # AWS default virtual-hosted style
    return f"https://{_S3_BUCKET}.s3.{_S3_REGION}.amazonaws.com/{key}"


def _guess_content_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"
