from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd


def _canonical_id(value: str) -> str:
    cleaned = str(value).strip()
    return re.sub(r"\.0+$", "", cleaned)


def _valid_email(val) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    return bool(s and re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", s))


def excel_load_customer_mapping() -> str:
    """
    Nacte mapovani customer_id -> emaily z Excel souboru.
    Vraci JSON objekt {customer_id: "email1, email2"}.
    Cesta a sloupce jsou konfigurovany pres env promenne.
    """
    excel_path = Path(os.getenv("MAPPING_EXCEL_PATH", "data/customer_emails.xlsx"))
    id_col = os.getenv("MAPPING_ID_COLUMN", "customer_id")
    email_col = os.getenv("MAPPING_EMAIL_COLUMN", "email")
    email_col2 = os.getenv("MAPPING_EMAIL_COLUMN2") or None

    if not excel_path.exists():
        raise FileNotFoundError(f"Mapping Excel nenalezen: {excel_path}")

    data = pd.read_excel(excel_path, dtype=str)
    missing = [c for c in (id_col, email_col) if c not in data.columns]
    if missing:
        raise ValueError(f"Excel neobsahuje sloupce: {', '.join(missing)}")

    mapping_lists: dict[str, list[str]] = {}
    mapping_seen: dict[str, set[str]] = {}

    for _, row in data.iterrows():
        raw_id = _canonical_id(str(row.get(id_col, "")).strip())
        if not raw_id:
            continue
        if raw_id not in mapping_lists:
            mapping_lists[raw_id] = []
            mapping_seen[raw_id] = set()

        emails: list[str] = []
        primary = row.get(email_col)
        if _valid_email(primary):
            emails.append(str(primary).strip())

        if email_col2 and email_col2 in data.columns:
            secondary = row.get(email_col2)
            if _valid_email(secondary):
                sec = str(secondary).strip()
                if sec not in emails:
                    emails.append(sec)

        for email in emails:
            norm = email.strip().lower()
            if norm not in mapping_seen[raw_id]:
                mapping_seen[raw_id].add(norm)
                mapping_lists[raw_id].append(email.strip())

    result = {cid: ", ".join(emails) for cid, emails in mapping_lists.items() if emails}
    return json.dumps(result)


def excel_load_skip_prefixes() -> str:
    """
    Nacte prefixni seznam Bill-To ID ze skip.xlsx pro preskoceni dokumentu.
    Vraci JSON pole retezcu ["prefix1", "prefix2"].
    Pokud skip.xlsx neexistuje, vraci prazdne pole.
    """
    skip_path = Path(os.getenv("SKIP_EXCEL_PATH", "inputs/skip.xlsx"))
    bill_to_col = os.getenv("SKIP_BILL_TO_COLUMN", "Bill-To")

    if not skip_path.exists():
        return json.dumps([])

    data = pd.read_excel(skip_path, dtype=str)
    if bill_to_col not in data.columns:
        return json.dumps([])

    prefixes: set[str] = set()
    for raw in data[bill_to_col].dropna().tolist():
        value = re.sub(r"\.0+$", "", str(raw).strip())
        if value:
            prefixes.add(value)

    # Seradit od nejdelsiho (specificke pred kratke pri porovnani)
    ordered = sorted(prefixes, key=len, reverse=True)
    return json.dumps(ordered)
