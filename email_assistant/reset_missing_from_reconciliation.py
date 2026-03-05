from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPORT_PATH = Path("_reconciliation_report.csv")
DB_PATH = Path("data/processing_state.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    if not REPORT_PATH.exists():
        print(f"Missing report file: {REPORT_PATH}")
        return 1

    with REPORT_PATH.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    missing_files = [r["file_name"].strip() for r in rows if r.get("file_name")]
    if not missing_files:
        print("No missing files found in reconciliation report.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(missing_files))
    now = utc_now()

    cur.execute(
        f"""
        UPDATE processed_files
        SET
            status = 'pending',
            email_sent = 0,
            moved_to_sent = 0,
            email_sent_at = NULL,
            moved_at = NULL,
            last_error = NULL,
            updated_at = ?
        WHERE file_name IN ({placeholders})
        """,
        [now, *missing_files],
    )
    updated = cur.rowcount

    conn.commit()

    cur.execute(
        f"SELECT COUNT(*) FROM processed_files WHERE file_name IN ({placeholders}) AND status = 'pending'",
        missing_files,
    )
    pending_count = cur.fetchone()[0]

    conn.close()

    print(f"Missing files in report: {len(missing_files)}")
    print(f"Rows updated in DB: {updated}")
    print(f"Rows now pending: {pending_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
