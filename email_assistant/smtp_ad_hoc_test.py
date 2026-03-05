from __future__ import annotations

import os
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip().strip('"\'')


def _smtp_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def _build_message(sender: str, recipient: str, tag: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"ADHOC SMTP TEST {tag}"
    msg["Message-ID"] = f"<{uuid.uuid4()}@hranipex.local>"
    msg.set_content(
        "Toto je ad-hoc test emailu z emailAssistant.\n"
        f"Tag: {tag}\n"
        f"Time: {datetime.now().isoformat(timespec='seconds')}\n"
    )
    return msg


def _build_message_with_pdf(sender: str, recipient: str, tag: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"ADHOC SMTP TEST PDF {tag}"
    msg["Message-ID"] = f"<{uuid.uuid4()}@hranipex.local>"
    msg.set_content("Toto je ad-hoc test emailu s PDF prilohou z emailAssistant.")

    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 36>>stream\nBT /F1 12 Tf 72 72 Td (SMTP TEST) Tj ET\nendstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"trailer<</Root 1 0 R/Size 5>>\nstartxref\n260\n%%EOF"
    )
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="smtp-test.pdf")
    return msg


def _send_message_with_trace(server: smtplib.SMTP, sender: str, recipient: str, message: EmailMessage) -> None:
    print(f"[INFO] subject={message['Subject']}")
    print(f"[INFO] message_id={message['Message-ID']}")

    code, resp = server.mail(sender)
    print(f"[SMTP] MAIL FROM -> {code} {resp.decode(errors='ignore')}")

    code, resp = server.rcpt(recipient)
    print(f"[SMTP] RCPT TO   -> {code} {resp.decode(errors='ignore')}")

    code, resp = server.data(message.as_string())
    print(f"[SMTP] DATA      -> {code} {resp.decode(errors='ignore')}")


def send_with_trace(host: str, port: int, use_tls: bool, username: str, password: str, sender: str, recipient: str) -> None:
    tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    message_plain = _build_message(sender, recipient, tag)
    message_pdf = _build_message_with_pdf(sender, recipient, tag)

    print(f"[INFO] host={host} port={port} tls={use_tls}")
    print(f"[INFO] from={sender} to={recipient}")
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.set_debuglevel(1)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username or password:
            server.login(username, password)

        print("[INFO] --- Sending plain test message ---")
        _send_message_with_trace(server, sender, recipient, message_plain)

        print("[INFO] --- Sending PDF attachment test message ---")
        _send_message_with_trace(server, sender, recipient, message_pdf)

    print("[DONE] Ad-hoc SMTP test finished.")


def main() -> int:
    load_dotenv(Path(__file__).with_name('.env'))

    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", "25"))
    use_tls = _smtp_bool("SMTP_USE_TLS", default=True)
    username = _env("SMTP_USERNAME")
    password = _env("SMTP_PASSWORD")
    sender = _env("EMAIL_FROM", default="jindrich.jasnsa.skript@hranipex.com")
    recipient = _env("TEST_RECIPIENT_EMAIL", default="jindrich.jansa@hranipex.com")

    if not host:
        raise ValueError("Missing SMTP_HOST")

    send_with_trace(host, port, use_tls, username, password, sender, recipient)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
