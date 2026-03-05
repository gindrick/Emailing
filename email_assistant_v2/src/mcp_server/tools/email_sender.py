from __future__ import annotations

import base64
import os
import smtplib
from email.message import EmailMessage


def smtp_send_email(
    to_recipients: str,
    subject: str,
    body: str,
    pdf_b64: str,
    file_name: str,
    bcc_recipients: str = "",
) -> str:
    """
    Odesle email s PDF prilohou pres SMTP.
    to_recipients: emaily oddelene carkou (jiz vyresene - test nebo produkcni)
    bcc_recipients: emaily oddelene carkou pro BCC (volitelne)
    pdf_b64: obsah PDF zakodovany v base64
    Vraci 'OK' nebo chybovou zpravu.
    """
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "y", "on"}
    email_from = os.getenv("EMAIL_FROM", smtp_username or "noreply@localhost")

    def _split(raw: str) -> list[str]:
        if not raw:
            return []
        import re
        parts = re.split(r"[;,]", raw)
        return [p.strip() for p in parts if p.strip()]

    recipient_list = _split(to_recipients)
    bcc_list = _split(bcc_recipients)

    if not recipient_list:
        raise ValueError("Zadni prijemce emailu")

    all_recipients = list(recipient_list)
    for addr in bcc_list:
        if addr not in all_recipients:
            all_recipients.append(addr)

    pdf_bytes = base64.b64decode(pdf_b64)

    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = ", ".join(recipient_list)
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=file_name,
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if smtp_username or smtp_password:
            server.login(smtp_username, smtp_password)
        server.send_message(msg, to_addrs=all_recipients)

    return "OK"


def smtp_send_plain_email(to_recipients: str, subject: str, body: str) -> str:
    """
    Odesle plain-text email bez prilohy (napr. souhrnny report).
    to_recipients: emaily oddelene carkou.
    Vraci 'OK' nebo chybovou zpravu.
    """
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "y", "on"}
    email_from = os.getenv("EMAIL_FROM", smtp_username or "noreply@localhost")

    import re
    recipient_list = [p.strip() for p in re.split(r"[;,]", to_recipients) if p.strip()]
    if not recipient_list:
        raise ValueError("Zadni prijemce emailu")

    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = ", ".join(recipient_list)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if smtp_username or smtp_password:
            server.login(smtp_username, smtp_password)
        server.send_message(msg)

    return "OK"
