from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional


class MailError(Exception):
    pass


def send_email(cfg: Dict, subject: str, text: str, html: str) -> None:
    smtp_cfg = cfg.get("smtp", {})
    host = smtp_cfg.get("host")
    port = int(smtp_cfg.get("port", 465))
    use_tls = bool(smtp_cfg.get("use_tls", True))
    sender = smtp_cfg.get("sender_email")
    receiver = smtp_cfg.get("receiver_email")
    password_env = smtp_cfg.get("password_env", "SMTP_PASSWORD")
    password = os.getenv(password_env)

    if not host or not sender or not receiver:
        raise MailError("SMTP host/sender/receiver not configured")
    if not password:
        raise MailError("SMTP password not found in environment")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    if use_tls:
        server = smtplib.SMTP_SSL(host, port)
    else:
        server = smtplib.SMTP(host, port)
        server.starttls()
    try:
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass

