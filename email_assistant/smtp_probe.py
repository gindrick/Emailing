from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip().strip("\"'")


def main() -> int:
    load_dotenv(Path(__file__).with_name('.env'))

    host = _env('SMTP_HOST')
    port = int(_env('SMTP_PORT', '25'))
    use_tls = _env('SMTP_USE_TLS', 'true').lower() in {'1', 'true', 'yes', 'y', 'on'}
    username = _env('SMTP_USERNAME')
    password = _env('SMTP_PASSWORD')
    sender = _env('EMAIL_FROM', 'noreply@hranipex.com')
    recipient = _env('TEST_RECIPIENT_EMAIL', 'jindrich.jansa@hranipex.com')

    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = f"SMTP PROBE {datetime.now().isoformat(timespec='seconds')}"
    msg.set_content('Test SMTP doruceni z emailAssistant (bez prilohy).')

    print(f"[INFO] SMTP host={host} port={port} tls={use_tls} sender={sender} recipient={recipient}")

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.set_debuglevel(1)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username or password:
            server.login(username, password)
        result = server.sendmail(sender, [recipient], msg.as_string())
        print(f"[INFO] sendmail result={result}")

    print('[DONE] Probe completed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
