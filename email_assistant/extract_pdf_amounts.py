from __future__ import annotations

import argparse
import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import pdfplumber
from dotenv import load_dotenv

from main import EXPORT_DIR, GraphClient, Settings, resolve_statements_source_folder_path

TABLE_HEADER_PATTERN = re.compile(
    r"Invoice\s+S\.order\s+Date\s+Due\s+Date\s+Amount\s+Amount\s+Open\s+Curr",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\d{2}/\d{2}/\d{4}")
CURRENCY_PATTERN = re.compile(r"(-?[0-9][0-9.,]*)\s+(GBP|EUR|USD|CAD|AUD|NZD|CZK|PLN|HUF|RON|CHF|SEK|NOK|DKK|[A-Z]{3})\b")
CUSTOMER_ID_IN_NAME = re.compile(r"(\d{5,})")
CUSTOMER_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bill\s*To\s*(\d{5,})", re.IGNORECASE),
    re.compile(r"Customer\s*ID\s*(\d{5,})", re.IGNORECASE),
    re.compile(r"Customer\s*(\d{5,})", re.IGNORECASE),
)


@dataclass
class ExtractionResult:
    file_name: str
    item_id: str
    customer_id_from_name: str | None
    customer_id_from_pdf: str | None
    amount_open: float | None
    currency_code: str | None
    amount_rows_detected: int
    error: str | None = None

    def to_row(self) -> dict[str, str | float | None]:
        return {
            "file_name": self.file_name,
            "item_id": self.item_id,
            "customer_id_from_name": self.customer_id_from_name,
            "customer_id_from_pdf": self.customer_id_from_pdf,
            "amount_open": self.amount_open,
            "currency_code": self.currency_code,
            "amount_rows_detected": self.amount_rows_detected,
            "error": self.error,
        }


DEFAULT_OUTPUT_FILE = EXPORT_DIR / "_amount_open_report.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download all Statements PDFs from SharePoint, extract Bill-To number and Amount "
            "Open values, and export the aggregated data into an Excel report."
        )
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_FILE),
        help=f"Target Excel file (default: {DEFAULT_OUTPUT_FILE})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for number of PDFs to process (useful for tests)",
    )
    return parser.parse_args()


def extract_text_pages(content: bytes) -> Iterable[str]:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            yield text


def extract_customer_id_from_text(text: str) -> str | None:
    for pattern in CUSTOMER_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def extract_customer_id_from_name(file_name: str) -> str | None:
    match = CUSTOMER_ID_IN_NAME.search(file_name)
    if match:
        return match.group(1)
    return None


def normalize_number(value: str) -> float:
    return float(value.replace(",", ""))


def extract_amount_open(text: str) -> tuple[float | None, str | None, int]:
    total = 0.0
    currency_counter: Counter[str] = Counter()
    rows = 0
    in_table = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if TABLE_HEADER_PATTERN.search(line):
            in_table = True
            continue
        if in_table:
            if line.lower().startswith("summary"):
                in_table = False
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            if not (DATE_PATTERN.fullmatch(parts[2]) and DATE_PATTERN.fullmatch(parts[3])):
                continue
            amount_open_raw = parts[-2]
            currency = parts[-1]
            try:
                amount_open = normalize_number(amount_open_raw)
            except ValueError:
                continue
            total += amount_open
            currency_counter[currency] += 1
            rows += 1

    if rows == 0:
        return None, None, 0

    currency_code = currency_counter.most_common(1)[0][0]
    return round(total, 2), currency_code, rows


def process_pdf(graph: GraphClient, drive_id: str, item: dict) -> ExtractionResult:
    file_name = item.get("name", "")
    item_id = item.get("id", "")
    if not item_id:
        raise ValueError(f"Item missing 'id': {item}")

    customer_from_name = extract_customer_id_from_name(file_name)

    try:
        content = graph.download_file(drive_id, item_id)
        text = "\n".join(extract_text_pages(content))
        customer_from_pdf = extract_customer_id_from_text(text)
        amount_open, currency_code, rows = extract_amount_open(text)
        return ExtractionResult(
            file_name=file_name,
            item_id=item_id,
            customer_id_from_name=customer_from_name,
            customer_id_from_pdf=customer_from_pdf,
            amount_open=amount_open,
            currency_code=currency_code,
            amount_rows_detected=rows,
        )
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(
            file_name=file_name,
            item_id=item_id,
            customer_id_from_name=customer_from_name,
            customer_id_from_pdf=None,
            amount_open=None,
            currency_code=None,
            amount_rows_detected=0,
            error=str(exc),
        )


def main() -> int:
    args = parse_args()
    load_dotenv()
    settings = Settings.from_env()
    graph = GraphClient(settings)

    site_id = graph.get_site_id(settings.site_hostname, settings.site_path)
    drive_id = graph.resolve_drive_id(site_id, settings.drive_id, settings.drive_name)
    source_folder = resolve_statements_source_folder_path(graph, drive_id, settings.source_folder_path)

    pdf_items = graph.list_pdfs_in_folder(drive_id, source_folder)
    pdf_items.sort(key=lambda item: item.get("name", ""))

    if args.limit is not None:
        pdf_items = pdf_items[: args.limit]

    print(f"Found {len(pdf_items)} PDF files in {source_folder}.")

    results: list[ExtractionResult] = []
    for idx, item in enumerate(pdf_items, start=1):
        file_name = item.get("name", "<unknown>")
        print(f"[{idx}/{len(pdf_items)}] Processing {file_name}...")
        result = process_pdf(graph, drive_id, item)
        if result.error:
            print(f"    [WARN] Failed to extract data: {result.error}")
        results.append(result)

    if not results:
        print("No data extracted; nothing to export.")
        return 0

    df = pd.DataFrame([res.to_row() for res in results])
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)
    print(f"Exported {len(df)} rows to {output_path}.")

    errors = [res for res in results if res.error]
    if errors:
        print(f"Completed with {len(errors)} files that require attention. See Excel for details.")
    else:
        print("Completed successfully with no extraction errors.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
