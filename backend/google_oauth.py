from __future__ import annotations

import logging

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from settings import GOOGLE_CLIENT_ID

log = logging.getLogger(__name__)

_request = google_requests.Request()


def verify_google_token(credential: str) -> dict | None:
    """Verify a Google Identity Services ID token and return its claims, or None if invalid."""
    if not GOOGLE_CLIENT_ID:
        return None
    try:
        claims = id_token.verify_oauth2_token(credential, _request, GOOGLE_CLIENT_ID)
    except ValueError:
        # A malformed/expired/wrong-audience token — expected and frequent
        # enough (stale client-side tokens) that it's not worth logging.
        return None
    except Exception as exc:
        # Anything else (network failure fetching Google's certs, etc.) —
        # treat as "couldn't verify" like every other outbound call in this
        # codebase, but log it since it points at an infra issue, not a bad token.
        log.warning("Google token verification failed: %s", exc)
        return None
    if not claims.get("email_verified"):
        return None
    return claims
