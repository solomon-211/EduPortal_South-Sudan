from __future__ import annotations

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from settings import GOOGLE_CLIENT_ID

_request = google_requests.Request()


def verify_google_token(credential: str) -> dict | None:
    """Verify a Google Identity Services ID token and return its claims, or None if invalid."""
    if not GOOGLE_CLIENT_ID:
        return None
    try:
        claims = id_token.verify_oauth2_token(credential, _request, GOOGLE_CLIENT_ID)
    except ValueError:
        return None
    if not claims.get("email_verified"):
        return None
    return claims
