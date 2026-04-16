# email_service.py - Gmail SMTP email sender for Clau Trading Backend.
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, otp: str) -> bool:
    """
    Send a 6-digit password reset OTP to the user's email via Gmail SMTP.
    Returns True on success, False on any failure (caller decides whether to surface the error).
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured — skipping password reset email")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Clau — Password Reset Code"
        msg["From"]    = SMTP_USER
        msg["To"]      = to_email

        text_body = (
            f"Your Clau password reset code is: {otp}\n\n"
            "This code expires in 15 minutes.\n"
            "If you did not request a password reset, you can safely ignore this email."
        )
        html_body = f"""
<html>
  <body style="font-family:sans-serif;max-width:480px;margin:40px auto;color:#333">
    <h2 style="color:#1a73e8">Clau Password Reset</h2>
    <p>Use the code below to reset your password. It expires in <strong>15 minutes</strong>.</p>
    <div style="font-size:36px;letter-spacing:10px;font-family:monospace;
                background:#f1f3f4;padding:16px 24px;border-radius:8px;
                display:inline-block;margin:16px 0">{otp}</div>
    <p style="color:#888;font-size:13px">
      If you didn't request this, you can safely ignore this email.
    </p>
  </body>
</html>
"""
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        logger.info("Password reset email sent to %s", to_email)
        return True

    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
        return False
