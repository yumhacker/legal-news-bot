"""Отправка email-уведомлений через Gmail SMTP.

Работает, только если в .env заполнены GMAIL_FROM и GMAIL_APP_PASSWORD
(пароль приложения: https://myaccount.google.com/apppasswords).
"""
import logging
import smtplib
from email.mime.text import MIMEText

import config

log = logging.getLogger("notifier")


def email_enabled() -> bool:
    return bool(config.GMAIL_FROM and config.GMAIL_APP_PASSWORD and config.EMAIL_TO)


def send_email(subject: str, html_body: str) -> None:
    """Синхронная отправка; вызывать через asyncio.to_thread()."""
    if not email_enabled():
        return
    msg = MIMEText(html_body.replace("\n", "<br>"), "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_FROM
    msg["To"] = config.EMAIL_TO
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(config.GMAIL_FROM, config.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        log.info("Email отправлен: %s", subject)
    except Exception:
        log.exception("Не удалось отправить email")
