"""Local-disk storage backend (default / fallback)."""
from __future__ import annotations

from pathlib import Path


def save(dest_dir: Path, filename: str, stream) -> str:
    """Write *stream* to dest_dir/filename. Returns the relative URL path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename).write_bytes(stream.read())
    # URL is built by the caller from the filename; we just confirm the name.
    return filename


def public_url(url_path: str) -> str:
    """Local files are served directly by Flask — return the path unchanged."""
    return url_path
