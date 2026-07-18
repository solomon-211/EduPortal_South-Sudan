"""Storage abstraction — auto-selects S3 or local disk based on env vars.

Usage (anywhere in the app):
    from storage import save_file, public_url

    stored_key = save_file(dest_dir, filename, file_stream)
    url        = public_url(stored_key)
"""
from __future__ import annotations

import os
from pathlib import Path

_USE_S3 = bool(os.environ.get("S3_BUCKET") and os.environ.get("S3_ACCESS_KEY"))

if _USE_S3:
    from storage.s3 import save as _save, public_url as _public_url
else:
    from storage.local import save as _save, public_url as _public_url


def save_file(dest_dir: Path, filename: str, stream) -> str:
    """Persist *stream* and return the stored key / relative path."""
    return _save(dest_dir, filename, stream)


def public_url(stored_key: str) -> str:
    """Resolve a stored key to a publicly accessible URL."""
    return _public_url(stored_key)


def using_s3() -> bool:
    return _USE_S3
