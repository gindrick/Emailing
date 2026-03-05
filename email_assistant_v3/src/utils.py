from __future__ import annotations

import re


def extract_customer_id_from_filename_start(filename_without_ext: str) -> str | None:
    """Extrahuje zakaznicke ID ze zacatku nazvu souboru (prvni alfanumericka sekvence)."""
    match = re.match(r"^\s*([A-Za-z0-9]+)", filename_without_ext)
    if not match:
        return None
    value = canonical_customer_id(match.group(1).strip())
    return value if value else None


def canonical_customer_id(value: str | None) -> str:
    """Normalizuje customer ID - odstrani trailing .0 apod."""
    if not value:
        return ""
    cleaned = str(value).strip()
    cleaned = re.sub(r"\.0+$", "", cleaned)
    return cleaned


def normalize_customer_id(value: str | None) -> str:
    """Normalizuje customer ID pro porovnani (lowercase, bez mezer)."""
    if not value:
        return ""
    normalized = str(value).strip().lower().replace(" ", "")
    normalized = re.sub(r"\.0+$", "", normalized)
    return normalized


def parse_recipient_list(raw: str | None) -> list[str]:
    """Rozparsuje retezec emailu oddeleny carkou/strednik na seznam."""
    if not raw:
        return []
    parts = re.split(r"[;,]", raw)
    return [p.strip() for p in parts if p and p.strip()]


def match_skip_prefix(value: str, prefixes: tuple[str, ...]) -> str | None:
    """Vrati prvni prefix ze skip listu ktery odpovida hodnote, nebo None."""
    for prefix in prefixes:
        if value.startswith(prefix):
            return prefix
    return None
