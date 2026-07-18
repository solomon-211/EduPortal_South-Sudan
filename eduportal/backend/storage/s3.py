"""S3-compatible storage backend (AWS S3 or Supabase Storage).

Required env vars:
    S3_BUCKET          — bucket name
    S3_REGION          — e.g. us-east-1  (or your Supabase region)
    S3_ACCESS_KEY      — AWS access key ID  /  Supabase service-role key
    S3_SECRET_KEY      — AWS secret access key  /  Supabase secret
    S3_ENDPOINT_URL    — leave blank for AWS; set to Supabase Storage URL for Supabase
                         e.g. https://<project>.supabase.co/storage/v1/s3

Optional:
    S3_PUBLIC_BASE_URL — base URL for public file access (auto-derived if blank)
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    _boto3_available = True
except ImportError:
    _boto3_available = False

_S3_BUCKET       = os.environ.get("S3_BUCKET", "")
_S3_REGION       = os.environ.get("S3_REGION", "us-east-1")
_S3_ACCESS_KEY   = os.environ.get("S3_ACCESS_KEY", "")
_S3_SECRET_KEY   = os.environ.get("S3_SECRET_KEY", "")
_S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")   # blank = AWS
_S3_PUBLIC_BASE  = os.environ.get("S3_PUBLIC_BASE_URL", "")

_client = None


def _get_client():
    global _client
    if _client is None:
        if not _boto3_available:
            raise RuntimeError("boto3 is not installed. Run: pip install boto3")
        kwargs: dict = dict(
            region_name=_S3_REGION,
            aws_access_key_id=_S3_ACCESS_KEY,
            aws_secret_access_key=_S3_SECRET_KEY,
        )
        if _S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = _S3_ENDPOINT_URL
        _client = boto3.client("s3", **kwargs)
    return _client


def save(dest_dir: Path, filename: str, stream) -> str:
    """Upload *stream* to S3 at <bucket>/<dest_dir.name>/<filename>.
    Returns the S3 object key (used as the stored path).
    """
    key = f"{dest_dir.name}/{filename}"
    _get_client().upload_fileobj(
        stream,
        _S3_BUCKET,
        key,
        ExtraArgs={"ContentType": _guess_content_type(filename)},
    )
    return key


def public_url(key: str) -> str:
    """Return the public HTTPS URL for an S3 object key."""
    if _S3_PUBLIC_BASE:
        return f"{_S3_PUBLIC_BASE.rstrip('/')}/{key}"
    if _S3_ENDPOINT_URL:
        # Supabase pattern: <endpoint>/object/public/<bucket>/<key>
        base = _S3_ENDPOINT_URL.replace("/storage/v1/s3", "/storage/v1")
        return f"{base}/object/public/{_S3_BUCKET}/{key}"
    # AWS default virtual-hosted style
    return f"https://{_S3_BUCKET}.s3.{_S3_REGION}.amazonaws.com/{key}"


def _guess_content_type(filename: str) -> str:
    import mimetypes
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"
