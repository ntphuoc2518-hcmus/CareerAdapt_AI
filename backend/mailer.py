"""Outbound account email (password reset).

Configure SMTP with CAREERADAPT_SMTP_HOST, CAREERADAPT_SMTP_PORT (default 587),
CAREERADAPT_SMTP_USER, CAREERADAPT_SMTP_PASSWORD and CAREERADAPT_MAIL_FROM.
Without SMTP, development builds print the message to the server console so the
flow can be tested locally; production never prints reset links.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("careeradapt.mail")

RESET_SUBJECT = {
    "vi": "Đặt lại mật khẩu CareerAdapt AI",
    "en": "Reset your CareerAdapt AI password",
}
RESET_BODY = {
    "vi": (
        "Xin chào {name},\n\n"
        "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản {email}.\n"
        "Mở liên kết sau trong vòng 30 phút để đặt mật khẩu mới:\n\n{link}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này; mật khẩu hiện tại vẫn giữ nguyên."
    ),
    "en": (
        "Hello {name},\n\n"
        "We received a request to reset the password for {email}.\n"
        "Open this link within 30 minutes to choose a new password:\n\n{link}\n\n"
        "If you did not request this, ignore this email; your current password stays the same."
    ),
}


def _is_production() -> bool:
    return os.getenv("CAREERADAPT_ENV", "development").lower() == "production"


def send_password_reset(email: str, name: str, link: str, language: str = "vi") -> None:
    language = language if language in RESET_BODY else "vi"
    body = RESET_BODY[language].format(name=name, email=email, link=link)
    host = os.getenv("CAREERADAPT_SMTP_HOST", "").strip()
    if not host:
        if _is_production():
            logger.error("Password reset requested but SMTP is not configured; no email was sent.")
        else:
            print(f"\n[DEV MAIL] To: {email}\n[DEV MAIL] Subject: {RESET_SUBJECT[language]}\n{body}\n", flush=True)
        return

    message = EmailMessage()
    message["From"] = os.getenv("CAREERADAPT_MAIL_FROM", "no-reply@careeradapt.local")
    message["To"] = email
    message["Subject"] = RESET_SUBJECT[language]
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("CAREERADAPT_SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            user = os.getenv("CAREERADAPT_SMTP_USER", "")
            if user:
                smtp.login(user, os.getenv("CAREERADAPT_SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        # The response stays generic either way, so a mail outage never reveals which emails exist.
        logger.exception("Password reset email could not be delivered.")
