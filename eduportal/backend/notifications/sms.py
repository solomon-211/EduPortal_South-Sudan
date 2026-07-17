from __future__ import annotations

import json
import urllib.parse
import urllib.request

from config.settings import AT_API_KEY, AT_SENDER_ID


def send_sms(phone: str, message: str) -> bool:
    if not AT_API_KEY:
        return False
    try:
        payload = urllib.parse.urlencode({
            "username": "sandbox" if "sandbox" in AT_API_KEY.lower() else "eduportal",
            "to": phone,
            "message": message,
            "from": AT_SENDER_ID,
        }).encode()
        req = urllib.request.Request(
            "https://api.africastalking.com/version1/messaging",
            data=payload,
            headers={"apiKey": AT_API_KEY, "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
            return result.get("SMSMessageData", {}).get("Recipients", [{}])[0].get("status") == "Success"
    except Exception:
        return False
