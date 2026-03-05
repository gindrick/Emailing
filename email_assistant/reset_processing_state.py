from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    env_path = Path(__file__).with_name('.env')
    load_dotenv(env_path)

    raw_db_path = os.getenv('STATE_DB_PATH', 'data/processing_state.db').strip().strip('"\'')
    db_path = Path(raw_db_path)
    if not db_path.is_absolute():
        db_path = Path(__file__).parent / db_path

    if not db_path.exists():
        print(f"[INFO] DB soubor neexistuje: {db_path}")
        return 0

    connection = sqlite3.connect(db_path)
    try:
        before = connection.execute("SELECT COUNT(1) FROM processed_files").fetchone()[0]
        connection.execute("DELETE FROM processed_files")
        connection.commit()
        after = connection.execute("SELECT COUNT(1) FROM processed_files").fetchone()[0]
    finally:
        connection.close()

    print(f"[OK] Stav vymazan v DB: {db_path}")
    print(f"[INFO] Pocet zaznamu pred: {before}, po: {after}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
