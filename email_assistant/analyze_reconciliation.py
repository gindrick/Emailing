from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from time import sleep

from dotenv import load_dotenv

from main import GraphClient, Settings, resolve_statements_source_folder_path


def list_pdfs_with_retry(graph: GraphClient, drive_id: str, folder_path: str, retries: int = 4) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return graph.list_pdfs_in_folder(drive_id, folder_path)
        except Exception as ex:
            last_error = ex
            if attempt < retries:
                sleep(2 * attempt)
    raise RuntimeError(f"Failed to list folder '{folder_path}' after {retries} attempts: {last_error}")


def find_last_log_hit(log_dir: Path, filename: str) -> str:
    hits: list[str] = []
    for path in sorted(log_dir.glob("run_*.log")):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if filename in line:
                        hits.append(f"{path.name}: {line.strip()}")
        except Exception:
            continue
    return hits[-1] if hits else ""


def main() -> int:
    load_dotenv()
    settings = Settings.from_env()
    graph = GraphClient(settings)

    site_id = graph.get_site_id(settings.site_hostname, settings.site_path)
    drive_id = graph.resolve_drive_id(site_id, settings.drive_id, settings.drive_name)

    source_folder = resolve_statements_source_folder_path(graph, drive_id, settings.source_folder_path)
    sent_folder = settings.sent_folder_path or f"{settings.source_folder_path}/sent"
    skipped_folder = f"{settings.source_folder_path}/skipped"
    redo_folder = f"{settings.source_folder_path}/redo"
    redo_error_folder = f"{settings.source_folder_path}/redo/error"

    source_items = list_pdfs_with_retry(graph, drive_id, source_folder)
    sent_items = list_pdfs_with_retry(graph, drive_id, sent_folder)
    skipped_items = list_pdfs_with_retry(graph, drive_id, skipped_folder)
    redo_items = list_pdfs_with_retry(graph, drive_id, redo_folder)
    redo_error_items = list_pdfs_with_retry(graph, drive_id, redo_error_folder)

    source_names = {item.get("name", "") for item in source_items if item.get("name")}
    sent_names = {item.get("name", "") for item in sent_items if item.get("name")}
    skipped_names = {item.get("name", "") for item in skipped_items if item.get("name")}
    redo_names = {item.get("name", "") for item in redo_items if item.get("name")}
    redo_error_names = {item.get("name", "") for item in redo_error_items if item.get("name")}

    covered_names = sent_names | skipped_names
    missing_names = sorted(source_names - covered_names)

    print("=== SharePoint folder counts ===")
    print(f"Source folder: {source_folder} -> {len(source_names)}")
    print(f"Sent folder:   {sent_folder} -> {len(sent_names)}")
    print(f"Skipped:       {skipped_folder} -> {len(skipped_names)}")
    print(f"Redo:          {redo_folder} -> {len(redo_names)}")
    print(f"Redo/error:    {redo_error_folder} -> {len(redo_error_names)}")
    print(f"Sent+Skipped:  {len(covered_names)}")
    print(f"Missing (source - (sent+skipped)): {len(missing_names)}")

    db_path = Path(settings.state_db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    report_rows: list[dict[str, str]] = []
    logs_dir = Path("logs")

    for file_name in missing_names:
        row = conn.execute(
            "SELECT file_name, customer_id, email_sent, moved_to_sent, status, last_error, updated_at "
            "FROM processed_files WHERE file_name = ?",
            (file_name,),
        ).fetchone()

        report_rows.append(
            {
                "file_name": file_name,
                "in_redo": "yes" if file_name in redo_names else "no",
                "in_redo_error": "yes" if file_name in redo_error_names else "no",
                "db_status": str(row["status"]) if row else "",
                "db_email_sent": str(row["email_sent"]) if row else "",
                "db_moved_to_sent": str(row["moved_to_sent"]) if row else "",
                "db_customer_id": str(row["customer_id"]) if row else "",
                "db_last_error": str(row["last_error"]) if row and row["last_error"] else "",
                "db_updated_at": str(row["updated_at"]) if row and row["updated_at"] else "",
                "last_log_hit": find_last_log_hit(logs_dir, file_name),
            }
        )

    conn.close()

    report_path = Path("_reconciliation_report.csv")
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file_name",
                "in_redo",
                "in_redo_error",
                "db_status",
                "db_email_sent",
                "db_moved_to_sent",
                "db_customer_id",
                "db_last_error",
                "db_updated_at",
                "last_log_hit",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"\nReport saved: {report_path}")
    if missing_names:
        print("\nMissing files:")
        for name in missing_names:
            print(f" - {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
