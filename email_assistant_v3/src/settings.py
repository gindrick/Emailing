from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _read_env(*names: str, required: bool = False, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        cleaned = value.strip().strip("\"'")
        if cleaned:
            return cleaned
    if required:
        raise ValueError(f"Chybi povinna promenna prostredi: {' nebo '.join(names)}")
    return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class AgentSettings:
    """Nastaveni pro agenta - ctena z .env souboru."""

    # LiteLLM
    litellm_base_url: str
    litellm_api_key: str
    litellm_model: str

    # MCP server
    mcp_server_url: str

    # Rezim zpracovani
    test_mode: bool
    test_recipient_email: str
    production_bcc: str | None
    batch_size: int

    # Sablony emailu
    email_subject_template: str
    email_body_template: str

    # Souhrnny report email po zpracovani (None = neposilat)
    summary_recipient_email: str | None

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            litellm_base_url=_read_env("LITELLM_BASE_URL", default="http://localhost:4000") or "http://localhost:4000",
            litellm_api_key=_read_env("LITELLM_API_KEY", "LITELLM_MASTER_KEY", default="sk-mysecretkey") or "sk-mysecretkey",
            litellm_model=_read_env("LITELLM_MODEL", default="oai-gpt-4.1-nano") or "oai-gpt-4.1-nano",
            mcp_server_url=_read_env("MCP_SERVER_URL", default="http://localhost:8002") or "http://localhost:8002",
            test_mode=_env_bool("TEST_MODE", default=True),
            test_recipient_email=_read_env("TEST_RECIPIENT_EMAIL", default="test@example.com") or "test@example.com",
            production_bcc=_read_env("PROD_BCC_EMAIL", "EMAIL_BCC", default=None),
            batch_size=max(1, int(_read_env("BATCH_SIZE", default="50") or "50")),
            email_subject_template=os.getenv("EMAIL_SUBJECT_TEMPLATE", "Vase dokumenty - zakaznik {customer_id}"),
            email_body_template=os.getenv(
                "EMAIL_BODY_TEMPLATE",
                "v priloze Vam posilame Vas dokument.\n\nS pozdravem,\nVas dodavatel",
            ),
            summary_recipient_email=_read_env("SUMMARY_RECIPIENT_EMAIL", default=None),
        )
