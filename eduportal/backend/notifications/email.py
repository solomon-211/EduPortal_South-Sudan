from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import SMTP_FROM, SMTP_HOST, SMTP_PASS, SMTP_PORT, SMTP_USER


def send_email(to: str, subject: str, body: str, html: str | None = None) -> bool:
    if not SMTP_HOST or not SMTP_USER:
        return False
    try:
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html, "html"))
        else:
            msg = MIMEText(body, "plain")  # type: ignore[assignment]
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception:
        return False


def send_verification_email(to: str, name: str, verify_url: str) -> bool:
    subject = "EduPortal — Verify your email address"
    plain = (
        f"Hello {name},\n\n"
        f"Thank you for registering on EduPortal South Sudan.\n\n"
        f"Please verify your email address by visiting the link below:\n{verify_url}\n\n"
        f"This link expires in 24 hours. If you did not create an account, ignore this email.\n\n"
        f"EduPortal South Sudan"
    )
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:24px;color:#1a1a1a">
  <h2 style="color:#1d6fa4">Verify your EduPortal account</h2>
  <p>Hello <strong>{name}</strong>,</p>
  <p>Thank you for registering on <strong>EduPortal South Sudan</strong>.</p>
  <p>Click the button below to verify your email address:</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{verify_url}"
       style="background:#1d6fa4;color:#fff;padding:12px 28px;border-radius:6px;
              text-decoration:none;font-weight:bold;display:inline-block">
      Verify Email Address
    </a>
  </p>
  <p style="font-size:13px;color:#555">
    Or copy this link into your browser:<br>
    <a href="{verify_url}" style="color:#1d6fa4">{verify_url}</a>
  </p>
  <p style="font-size:12px;color:#888">This link expires in 24 hours.<br>
  If you did not create an account, you can safely ignore this email.</p>
  <hr style="border:none;border-top:1px solid #eee;margin-top:32px">
  <p style="font-size:11px;color:#aaa;text-align:center">EduPortal South Sudan</p>
</body>
</html>"""
    return send_email(to, subject, plain, html)
