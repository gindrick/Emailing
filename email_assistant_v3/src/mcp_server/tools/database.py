from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

EXPORT_DIR = Path("output")

# Modul-level stav
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        raise RuntimeError("DB neni inicializovana. Zavolej db_initialize nejdrive.")
    return _conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_initialize() -> str:
    """
    Inicializuje SQLite databazi pro sledovani stavu zpracovani.
    Vytvori tabulku pokud neexistuje.
    Vraci 'OK'.
    """
    global _conn
    db_path = Path(os.getenv("STATE_DB_PATH", "data/processing_state.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(db_path)
    _conn.row_factory = sqlite3.Row
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            item_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            customer_id TEXT,
            customer_email TEXT,
            target_recipient TEXT,
            email_sent INTEGER NOT NULL DEFAULT 0,
            moved_to_sent INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            email_sent_at TEXT,
            moved_at TEXT
        )
    """)
    _conn.commit()
    return "OK"


def db_seed_items(items_json: str) -> str:
    """
    Vlozi nebo updatuje zaznamy PDF souboru v DB (upsert).
    items_json: JSON pole objektu [{id, name}]
    Vraci pocet zpracovanych zaznamu jako string.
    """
    conn = _get_conn()
    items = json.loads(items_json)
    now = _utc_now()
    count = 0
    for item in items:
        conn.execute("""
            INSERT INTO processed_files (item_id, file_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                file_name = excluded.file_name,
                updated_at = excluded.updated_at
        """, (item["id"], item["name"], now, now))
        count += 1
    conn.commit()
    return str(count)


def db_get_batch(item_ids_json: str) -> str:
    """
    Vrati seznam item_id k zpracovani (pending/failed stav, nepresunuty).
    item_ids_json: JSON pole retezcu - vsechny nalezene item_id
    Vraci JSON pole item_id k zpracovani.
    """
    conn = _get_conn()
    batch_size = max(1, int(os.getenv("BATCH_SIZE", "50")))
    item_ids: list[str] = json.loads(item_ids_json)
    if not item_ids:
        return json.dumps([])
    placeholders = ",".join(["?"] * len(item_ids))
    cursor = conn.execute(f"""
        SELECT item_id FROM processed_files
        WHERE item_id IN ({placeholders})
          AND moved_to_sent = 0
          AND status IN ('pending', 'failed', 'moved_to_redo', 'email_sent', 'sending', 'moving')
        ORDER BY created_at ASC
        LIMIT ?
    """, (*item_ids, batch_size))
    return json.dumps([str(row["item_id"]) for row in cursor.fetchall()])


def db_get_file_state(item_id: str) -> str:
    """
    Vrati aktualni stav zpracovani souboru jako JSON.
    """
    conn = _get_conn()
    cursor = conn.execute("SELECT * FROM processed_files WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        return json.dumps(None)
    return json.dumps(dict(row))


def db_ensure_file(item_id: str, file_name: str, customer_id: str, customer_email: str, target_recipient: str) -> str:
    """
    Ulozi nebo updatuje metadata souboru v DB.
    Vraci 'OK'.
    """
    conn = _get_conn()
    now = _utc_now()
    conn.execute("""
        INSERT INTO processed_files (
            item_id, file_name, customer_id, customer_email, target_recipient, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            file_name = excluded.file_name,
            customer_id = COALESCE(excluded.customer_id, processed_files.customer_id),
            customer_email = COALESCE(excluded.customer_email, processed_files.customer_email),
            target_recipient = COALESCE(excluded.target_recipient, processed_files.target_recipient),
            updated_at = excluded.updated_at
    """, (item_id, file_name, customer_id or None, customer_email or None, target_recipient or None, now, now))
    conn.commit()
    return "OK"


def db_mark_status(item_id: str, status: str, error_message: str = "") -> str:
    """
    Nastavi status zaznamu v DB.
    Vraci 'OK'.
    """
    conn = _get_conn()
    conn.execute(
        "UPDATE processed_files SET status = ?, last_error = ?, updated_at = ? WHERE item_id = ?",
        (status, error_message or None, _utc_now(), item_id),
    )
    conn.commit()
    return "OK"


def db_mark_email_sent(item_id: str) -> str:
    """Oznaci email jako odeslany. Vraci 'OK'."""
    conn = _get_conn()
    now = _utc_now()
    conn.execute("""
        UPDATE processed_files
        SET email_sent = 1, email_sent_at = ?, status = 'email_sent', last_error = NULL, updated_at = ?
        WHERE item_id = ?
    """, (now, now, item_id))
    conn.commit()
    return "OK"


def db_mark_moved(item_id: str) -> str:
    """Oznaci soubor jako presunuty do sent. Vraci 'OK'."""
    conn = _get_conn()
    now = _utc_now()
    conn.execute("""
        UPDATE processed_files
        SET moved_to_sent = 1, moved_at = ?, status = 'completed', last_error = NULL, updated_at = ?
        WHERE item_id = ?
    """, (now, now, item_id))
    conn.commit()
    return "OK"


def db_mark_redo(item_id: str, error_message: str = "") -> str:
    """Oznaci soubor jako presunuty do redo. Vraci 'OK'."""
    conn = _get_conn()
    now = _utc_now()
    conn.execute("""
        UPDATE processed_files
        SET moved_to_sent = 0, moved_at = ?, status = 'moved_to_redo', last_error = ?, updated_at = ?
        WHERE item_id = ?
    """, (now, error_message or None, now, item_id))
    conn.commit()
    return "OK"


def db_mark_skipped(item_id: str) -> str:
    """Oznaci soubor jako preskoceny (skip.xlsx). Vraci 'OK'."""
    conn = _get_conn()
    now = _utc_now()
    conn.execute("""
        UPDATE processed_files
        SET moved_to_sent = 0, moved_at = ?, status = 'skipped_bill_to', last_error = NULL, updated_at = ?
        WHERE item_id = ?
    """, (now, now, item_id))
    conn.commit()
    return "OK"


def db_get_summary() -> str:
    """
    Vrati souhrnne statistiky zpracovani z DB jako JSON.
    Obsahuje pocty a detail chybovych souboru pro informacni email.
    """
    conn = _get_conn()

    def _count(where: str) -> int:
        return conn.execute(f"SELECT COUNT(*) FROM processed_files WHERE {where}").fetchone()[0]

    total = _count("1=1")
    completed = _count("status = 'completed'")
    sent_only = _count("email_sent = 1 AND moved_to_sent = 0")
    skipped = _count("status = 'skipped_bill_to'")
    redo = _count("status = 'moved_to_redo'")
    failed = _count("status IN ('failed', 'error')")
    pending = _count("status IN ('pending', 'sending', 'moving')")

    # Detail souboru v chybe/redo
    cursor = conn.execute(
        "SELECT file_name, status, last_error FROM processed_files "
        "WHERE status IN ('moved_to_redo', 'failed', 'error') ORDER BY updated_at DESC LIMIT 50"
    )
    error_items = [
        {"file_name": row["file_name"], "status": row["status"], "error": row["last_error"] or ""}
        for row in cursor.fetchall()
    ]

    return json.dumps({
        "total": total,
        "completed": completed,
        "email_sent_pending_move": sent_only,
        "skipped": skipped,
        "redo": redo,
        "failed": failed,
        "pending": pending,
        "error_items": error_items,
    })


def db_export_reports() -> str:
    """
    Exportuje reporty do Excel souboru v output/ slozce.
    Vraci shrnutı exportovanych souboru.
    """
    conn = _get_conn()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    def _export(query: str, path: Path, sheet: str = "Sheet1") -> int:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        if rows:
            cols = rows[0].keys()
            df = pd.DataFrame([dict(r) for r in rows], columns=cols)
        else:
            cols = [d[0] for d in cursor.description] if cursor.description else []
            df = pd.DataFrame(columns=cols)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet)
        return len(rows)

    log_path = EXPORT_DIR / "_log.xlsx"
    sent_path = EXPORT_DIR / "_sent_report.xlsx"
    failed_path = EXPORT_DIR / "_failed_report.xlsx"

    _export("SELECT * FROM processed_files ORDER BY created_at", log_path)
    sent_count = _export(
        "SELECT item_id, file_name, customer_id, customer_email, target_recipient, email_sent_at, moved_at "
        "FROM processed_files WHERE email_sent = 1 ORDER BY email_sent_at",
        sent_path, "Sent"
    )
    failed_count = _export(
        "SELECT item_id, file_name, customer_id, status, last_error, updated_at "
        "FROM processed_files WHERE status IN ('moved_to_redo', 'error') ORDER BY updated_at",
        failed_path, "Failed"
    )

    return f"Exportovano: {log_path} | {sent_path} ({sent_count} docs) | {failed_path} ({failed_count} docs)"
