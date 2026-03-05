from __future__ import annotations

import io
import os
import re
import sqlite3
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import msal
import pandas as pd
import requests
from dotenv import load_dotenv


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
EXPORT_DIR = Path.cwd() / "output"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _folder_path_variants(folder_path: str) -> list[str]:
	cleaned = folder_path.strip().strip("/")
	if not cleaned:
		return []

	variants = [cleaned]
	prefix = "Shared Documents/"
	if cleaned.startswith(prefix):
		variants.append(cleaned[len(prefix) :])
	if cleaned == "Shared Documents":
		variants.append("")

	unique = []
	for variant in variants:
		if variant not in unique:
			unique.append(variant)
	return unique


def _require_env(name: str) -> str:
	value = os.getenv(name)
	if not value:
		raise ValueError(f"Chybi povinna promenna prostredi: {name}")
	return value


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


def _split_site_url(site_url: str) -> tuple[str, str]:
	parsed = urlparse(site_url)
	if not parsed.scheme or not parsed.netloc or not parsed.path:
		raise ValueError("Neplatna hodnota SHAREPOINT_SITE_URL")
	return parsed.netloc, parsed.path


def _normalize_folder_path(raw_folder: str, site_path: str) -> str:
	folder = raw_folder.strip()
	if not folder:
		raise ValueError("Prazdna hodnota pro SHAREPOINT_FOLDER_PATH/SP_SOURCE_FOLDER_PATH")

	if folder.startswith("http://") or folder.startswith("https://"):
		parsed = urlparse(folder)
		query = parse_qs(parsed.query)
		if "id" in query and query["id"]:
			folder = unquote(query["id"][0])
		else:
			folder = unquote(parsed.path)

	normalized_site = site_path if site_path.startswith("/") else f"/{site_path}"
	if folder.startswith(normalized_site):
		folder = folder[len(normalized_site) :]

	folder = folder.lstrip("/")
	if not folder:
		raise ValueError("Nelze odvodit cestu slozky z SHAREPOINT_FOLDER_PATH")
	return folder


@dataclass
class Settings:
	tenant_id: str
	client_id: str
	client_secret: str
	site_hostname: str
	site_path: str
	drive_id: str | None
	drive_name: str | None
	source_folder_path: str
	sent_folder_id: str | None
	sent_folder_path: str | None
	state_db_path: Path
	batch_size: int
	test_mode: bool
	test_recipient_email: str
	mapping_excel_path: Path
	mapping_id_column: str
	mapping_email_column: str
	mapping_email_column2: str | None
	production_bcc: str | None
	customer_id_regex: str | None
	smtp_host: str
	smtp_port: int
	smtp_username: str
	smtp_password: str
	smtp_use_tls: bool
	email_from: str
	email_subject_template: str
	email_body_template: str

	@classmethod
	def from_env(cls) -> "Settings":
		mapping_excel = _read_env("MAPPING_EXCEL_PATH", default="data/customer_emails.xlsx")
		smtp_username = _read_env("SMTP_USERNAME", default="") or ""

		site_url = _read_env("SHAREPOINT_SITE_URL")
		if site_url:
			site_hostname, site_path = _split_site_url(site_url)
		else:
			site_hostname = _read_env("SHAREPOINT_SITE_HOSTNAME", "SP_SITE_HOSTNAME", required=True)
			site_path = _read_env("SHAREPOINT_SITE_PATH", "SP_SITE_PATH", required=True)

		raw_folder_path = _read_env("SHAREPOINT_FOLDER_PATH", "SP_SOURCE_FOLDER_PATH", required=True)
		source_folder_path = _normalize_folder_path(raw_folder_path, site_path)

		raw_sent_folder_path = _read_env("SHAREPOINT_SENT_FOLDER_PATH", "SP_SENT_FOLDER_PATH")
		sent_folder_path = (
			_normalize_folder_path(raw_sent_folder_path, site_path) if raw_sent_folder_path else None
		)

		return cls(
			tenant_id=_read_env("AZURE_TENANT_ID", "MS_TENANT_ID", required=True),
			client_id=_read_env("AZURE_CLIENT_ID", "MS_CLIENT_ID", required=True),
			client_secret=_read_env("AZURE_CLIENT_SECRET", "MS_CLIENT_SECRET", required=True),
			site_hostname=site_hostname,
			site_path=site_path,
			drive_id=_read_env("SHAREPOINT_DRIVE_ID", "SP_DRIVE_ID"),
			drive_name=_read_env("SHAREPOINT_DRIVE_NAME", "SP_DRIVE_NAME"),
			source_folder_path=source_folder_path,
			sent_folder_id=_read_env("SHAREPOINT_SENT_FOLDER_ID", "SP_SENT_FOLDER_ID"),
			sent_folder_path=sent_folder_path,
			state_db_path=Path(_read_env("STATE_DB_PATH", default="data/processing_state.db") or "data/processing_state.db"),
			batch_size=max(1, int(_read_env("BATCH_SIZE", default="50") or "50")),
			test_mode=_env_bool("TEST_MODE", default=True),
			test_recipient_email=_read_env(
				"TEST_RECIPIENT_EMAIL",
				default="jindrich.jansa@hranipex.com",
			)
			or "jindrich.jansa@hranipex.com",
			mapping_excel_path=Path(mapping_excel),
			mapping_id_column=_read_env("MAPPING_ID_COLUMN", default="customer_id"),
			mapping_email_column=_read_env("MAPPING_EMAIL_COLUMN", default="email"),
			mapping_email_column2=_read_env("MAPPING_EMAIL_COLUMN2", default=None),
			production_bcc=_read_env("PROD_BCC_EMAIL", "EMAIL_BCC", default=None),
			customer_id_regex=os.getenv("CUSTOMER_ID_REGEX"),
			smtp_host=_require_env("SMTP_HOST"),
			smtp_port=int(os.getenv("SMTP_PORT", "587")),
			smtp_username=smtp_username,
			smtp_password=_read_env("SMTP_PASSWORD", default="") or "",
			smtp_use_tls=_env_bool("SMTP_USE_TLS", default=True),
			email_from=os.getenv("EMAIL_FROM", smtp_username or "noreply@localhost"),
			email_subject_template=os.getenv(
				"EMAIL_SUBJECT_TEMPLATE", "Dokument pro zakaznika {customer_id}"
			),
			email_body_template=os.getenv(
				"EMAIL_BODY_TEMPLATE",
				"Dobry den,\n\nv priloze posilame PDF dokument.\n\nS pozdravem",
			),
		)


class GraphClient:
	def __init__(self, settings: Settings) -> None:
		authority = f"https://login.microsoftonline.com/{settings.tenant_id}"
		self._app = msal.ConfidentialClientApplication(
			settings.client_id,
			authority=authority,
			client_credential=settings.client_secret,
		)
		self._scope = ["https://graph.microsoft.com/.default"]

	def _access_token(self) -> str:
		token_result = self._app.acquire_token_silent(self._scope, account=None)
		if not token_result:
			token_result = self._app.acquire_token_for_client(scopes=self._scope)
		token = token_result.get("access_token")
		if not token:
			raise RuntimeError(
				f"Nepodarilo se ziskat access token: {token_result.get('error_description', token_result)}"
			)
		return token

	def _request(self, method: str, url: str, **kwargs) -> requests.Response:
		headers = kwargs.pop("headers", {})
		headers["Authorization"] = f"Bearer {self._access_token()}"
		response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
		response.raise_for_status()
		return response

	def get_site_id(self, hostname: str, site_path: str) -> str:
		normalized = site_path if site_path.startswith("/") else f"/{site_path}"
		url = f"{GRAPH_BASE_URL}/sites/{hostname}:{normalized}"
		response = self._request("GET", url)
		return response.json()["id"]

	def resolve_drive_id(self, site_id: str, drive_id: str | None, drive_name: str | None) -> str:
		if drive_id:
			return drive_id
		if not drive_name:
			raise ValueError("Neni nastaveno SP_DRIVE_ID ani SP_DRIVE_NAME")

		url = f"{GRAPH_BASE_URL}/sites/{site_id}/drives"
		response = self._request("GET", url)
		for drive in response.json().get("value", []):
			if drive.get("name") == drive_name:
				return drive["id"]
		raise ValueError(f"Drive s nazvem '{drive_name}' nebyl nalezen.")

	def list_pdfs_in_folder(self, drive_id: str, folder_path: str) -> list[dict]:
		params = {"$top": "999"}
		last_error = None

		for variant in _folder_path_variants(folder_path):
			url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{variant}:/children"
			try:
				response = self._request("GET", url, params=params)
				files = []
				for item in response.json().get("value", []):
					name = item.get("name", "")
					if item.get("file") and name.lower().endswith(".pdf"):
						files.append(item)
				return files
			except requests.HTTPError as error:
				if error.response is not None and error.response.status_code == 404:
					last_error = error
					continue
				raise

		if last_error:
			raise last_error
		raise ValueError(f"Neplatna cesta zdrojove slozky: {folder_path}")

	def list_children_in_folder(self, drive_id: str, folder_path: str) -> list[dict]:
		params = {"$top": "999"}
		last_error = None

		for variant in _folder_path_variants(folder_path):
			url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{variant}:/children"
			try:
				response = self._request("GET", url, params=params)
				return response.json().get("value", [])
			except requests.HTTPError as error:
				if error.response is not None and error.response.status_code == 404:
					last_error = error
					continue
				raise

		if last_error:
			raise last_error
		raise ValueError(f"Neplatna cesta slozky: {folder_path}")

	def resolve_folder_id(self, drive_id: str, folder_path: str) -> str:
		last_error = None
		for variant in _folder_path_variants(folder_path):
			url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{variant}"
			try:
				response = self._request("GET", url)
				payload = response.json()
				if not payload.get("folder"):
					raise ValueError(f"Cilova slozka neni folder: {folder_path}")
				return payload["id"]
			except requests.HTTPError as error:
				if error.response is not None and error.response.status_code == 404:
					last_error = error
					continue
				raise

		if last_error:
			raise last_error
		raise ValueError(f"Neplatna cesta cilove slozky: {folder_path}")

	def download_file(self, drive_id: str, item_id: str) -> bytes:
		url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content"
		response = self._request("GET", url)
		return response.content

	def validate_folder_id(self, drive_id: str, folder_id: str) -> None:
		url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{folder_id}"
		response = self._request("GET", url)
		payload = response.json()
		if not payload.get("folder"):
			raise ValueError(f"Polozka {folder_id} neni slozka")

	def move_item_to_folder(self, drive_id: str, item_id: str, target_folder_id: str) -> None:
		url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}"
		payload = {"parentReference": {"id": target_folder_id}}
		self._request("PATCH", url, json=payload)

	def upload_file_to_folder(self, drive_id: str, folder_id: str, file_name: str, content: bytes) -> None:
		escaped_name = quote(file_name, safe="")
		url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{folder_id}:/{escaped_name}:/content"
		headers = {"Content-Type": "application/pdf"}
		self._request("PUT", url, headers=headers, data=content)

	def copy_item_to_folder(self, drive_id: str, item_id: str, target_folder_id: str, file_name: str) -> None:
		content = self.download_file(drive_id, item_id)
		self.upload_file_to_folder(drive_id, target_folder_id, file_name, content)

	def ensure_folder_path(self, drive_id: str, folder_path: str) -> str:
		try:
			return self.resolve_folder_id(drive_id, folder_path)
		except requests.HTTPError as error:
			if error.response is None or error.response.status_code != 404:
				raise

		cleaned = folder_path.strip("/")
		if not cleaned or "/" not in cleaned:
			raise

		parent_path, folder_name = cleaned.rsplit("/", 1)
		parent_id = self.resolve_folder_id(drive_id, parent_path)
		url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{parent_id}/children"
		payload = {
			"name": folder_name,
			"folder": {},
			"@microsoft.graph.conflictBehavior": "replace",
		}
		response = self._request("POST", url, json=payload)
		return response.json()["id"]


class ProcessingState:
	def __init__(self, db_path: Path) -> None:
		self._db_path = db_path
		db_path.parent.mkdir(parents=True, exist_ok=True)
		self._connection = sqlite3.connect(db_path)
		self._connection.row_factory = sqlite3.Row
		self._initialize()

	def _initialize(self) -> None:
		self._connection.execute(
			"""
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
			"""
		)
		self._connection.commit()

	@staticmethod
	def _utc_now() -> str:
		return datetime.now(timezone.utc).isoformat()

	def get(self, item_id: str) -> sqlite3.Row | None:
		cursor = self._connection.execute(
			"SELECT * FROM processed_files WHERE item_id = ?",
			(item_id,),
		)
		return cursor.fetchone()

	def ensure_exists(self, item_id: str, file_name: str, customer_id: str | None, customer_email: str | None, target_recipient: str | None) -> None:
		now = self._utc_now()
		self._connection.execute(
			"""
			INSERT INTO processed_files (
				item_id, file_name, customer_id, customer_email, target_recipient, created_at, updated_at
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(item_id) DO UPDATE SET
				file_name = excluded.file_name,
				customer_id = COALESCE(excluded.customer_id, processed_files.customer_id),
				customer_email = COALESCE(excluded.customer_email, processed_files.customer_email),
				target_recipient = COALESCE(excluded.target_recipient, processed_files.target_recipient),
				updated_at = excluded.updated_at
			""",
			(item_id, file_name, customer_id, customer_email, target_recipient, now, now),
		)
		self._connection.commit()

	def next_batch_item_ids(self, candidate_item_ids: list[str], limit: int) -> list[str]:
		if not candidate_item_ids:
			return []
		placeholders = ",".join(["?"] * len(candidate_item_ids))
		params: list[str | int] = list(candidate_item_ids)
		params.append(limit)
		cursor = self._connection.execute(
			f"""
			SELECT item_id
			FROM processed_files
			WHERE item_id IN ({placeholders})
			  AND moved_to_sent = 0
			  AND status IN ('pending', 'failed', 'moved_to_redo', 'email_sent', 'sending', 'moving')
			ORDER BY created_at ASC
			LIMIT ?
			""",
			tuple(params),
		)
		return [str(row["item_id"]) for row in cursor.fetchall()]

	def mark_status(self, item_id: str, status: str, error_message: str | None = None) -> None:
		now = self._utc_now()
		self._connection.execute(
			"""
			UPDATE processed_files
			SET status = ?, last_error = ?, updated_at = ?
			WHERE item_id = ?
			""",
			(status, error_message, now, item_id),
		)
		self._connection.commit()

	def mark_email_sent(self, item_id: str) -> None:
		now = self._utc_now()
		self._connection.execute(
			"""
			UPDATE processed_files
			SET email_sent = 1,
				email_sent_at = ?,
				status = 'email_sent',
				last_error = NULL,
				updated_at = ?
			WHERE item_id = ?
			""",
			(now, now, item_id),
		)
		self._connection.commit()

	def mark_moved(self, item_id: str) -> None:
		now = self._utc_now()
		self._connection.execute(
			"""
			UPDATE processed_files
			SET moved_to_sent = 1,
				moved_at = ?,
				status = 'completed',
				last_error = NULL,
				updated_at = ?
			WHERE item_id = ?
			""",
			(now, now, item_id),
		)
		self._connection.commit()

	def mark_moved_to_redo(self, item_id: str, error_message: str | None = None) -> None:
		now = self._utc_now()
		self._connection.execute(
			"""
			UPDATE processed_files
			SET moved_to_sent = 0,
				moved_at = ?,
				status = 'moved_to_redo',
				last_error = ?,
				updated_at = ?
			WHERE item_id = ?
			""",
			(now, error_message, now, item_id),
		)
		self._connection.commit()

	def mark_moved_to_skipped(self, item_id: str) -> None:
		now = self._utc_now()
		self._connection.execute(
			"""
			UPDATE processed_files
			SET moved_to_sent = 0,
				moved_at = ?,
				status = 'skipped_bill_to',
				last_error = NULL,
				updated_at = ?
			WHERE item_id = ?
			""",
			(now, now, item_id),
		)
		self._connection.commit()

	def export_to_excel(self, path: Path | None = None) -> None:
		"""Export current processed_files table to an Excel file.
		If `path` is None, writes to project root `_log.xlsx`.
		"""
		if path is None:
			path = EXPORT_DIR / "_log.xlsx"
		cursor = self._connection.execute("SELECT * FROM processed_files ORDER BY created_at")
		rows = cursor.fetchall()
		if not rows:
			# create an empty dataframe with columns if no rows
			cols = [d[0] for d in cursor.description] if cursor.description else []
			df = pd.DataFrame(columns=cols)
		else:
			cols = rows[0].keys()
			df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
		# ensure parent exists
		path.parent.mkdir(parents=True, exist_ok=True)
		# write excel
		with pd.ExcelWriter(path, engine="openpyxl") as writer:
			df.to_excel(writer, index=False)

	def export_sent_report(self, path: Path | None = None) -> int:
		"""Export successfully sent documents to _sent_report.xlsx.
		Returns count of sent documents.
		"""
		if path is None:
			path = EXPORT_DIR / "_sent_report.xlsx"
		cursor = self._connection.execute(
			"SELECT item_id, file_name, customer_id, customer_email, target_recipient, "
			"email_sent_at, moved_at FROM processed_files WHERE email_sent = 1 ORDER BY email_sent_at"
		)
		rows = cursor.fetchall()
		sent_count = len(rows)
		if rows:
			cols = rows[0].keys()
			df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
		else:
			df = pd.DataFrame(columns=["item_id", "file_name", "customer_id", "customer_email", 
										"target_recipient", "email_sent_at", "moved_at"])
		path.parent.mkdir(parents=True, exist_ok=True)
		with pd.ExcelWriter(path, engine="openpyxl") as writer:
			df.to_excel(writer, index=False, sheet_name="Sent")
		return sent_count

	def export_failed_report(self, path: Path | None = None) -> int:
		"""Export failed/error documents to _failed_report.xlsx.
		Returns count of failed documents.
		"""
		if path is None:
			path = EXPORT_DIR / "_failed_report.xlsx"
		cursor = self._connection.execute(
			"SELECT item_id, file_name, customer_id, status, last_error, updated_at "
			"FROM processed_files WHERE status IN ('moved_to_redo', 'error') ORDER BY updated_at"
		)
		rows = cursor.fetchall()
		failed_count = len(rows)
		if rows:
			cols = rows[0].keys()
			df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
		else:
			df = pd.DataFrame(columns=["item_id", "file_name", "customer_id", "status", "last_error", "updated_at"])
		path.parent.mkdir(parents=True, exist_ok=True)
		with pd.ExcelWriter(path, engine="openpyxl") as writer:
			df.to_excel(writer, index=False, sheet_name="Failed")
		return failed_count

	def export_queue_report(self, item_ids: list[str], path: Path | None = None) -> None:
		"""Export the queue of documents to be processed.
		Shows all items with their current status from DB.
		"""
		if path is None:
			path = EXPORT_DIR / "_queue.xlsx"
		
		# Build a query to get all items with their statuses
		placeholders = ",".join(["?" for _ in item_ids])
		cursor = self._connection.execute(
			f"SELECT item_id, file_name, customer_id, status, email_sent, moved_to_sent, last_error "
			f"FROM processed_files WHERE item_id IN ({placeholders}) ORDER BY created_at",
			item_ids
		)
		rows = cursor.fetchall()
		if rows:
			cols = rows[0].keys()
			df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
		else:
			df = pd.DataFrame(item_ids, columns=["item_id"])
		
		path.parent.mkdir(parents=True, exist_ok=True)
		with pd.ExcelWriter(path, engine="openpyxl") as writer:
			df.to_excel(writer, index=False, sheet_name="Queue")

	def close(self) -> None:
		self._connection.close()


def load_customer_email_map(
	excel_path: Path,
	id_column: str,
	email_column: str,
	email_column2: str | None = None,
) -> dict[str, str]:
	if not excel_path.exists():
		raise FileNotFoundError(f"Pomocny Excel nebyl nalezen: {excel_path}")

	data = pd.read_excel(excel_path, dtype=str)
	# required columns: id and first email
	missing = [column for column in (id_column, email_column) if column not in data.columns]
	if missing:
		raise ValueError(f"Excel neobsahuje sloupce: {', '.join(missing)}")

	# helper to validate a simple email
	def _valid_email(val: str | float) -> bool:
		if val is None:
			return False
		s = str(val).strip()
		if not s:
			return False
		# simple validation
		return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", s))

	mapping_lists: dict[str, list[str]] = {}
	mapping_seen: dict[str, set[str]] = {}
	invalid_rows: list[dict] = []
	for idx, row in data.iterrows():
		raw_id = _canonical_customer_id(str(row.get(id_column, "")).strip())
		if not raw_id:
			continue
		if raw_id not in mapping_lists:
			mapping_lists[raw_id] = []
			mapping_seen[raw_id] = set()

		emails: list[str] = []
		primary = row.get(email_column)
		primary_valid = primary is not None and _valid_email(primary)
		secondary_valid = False
		if primary_valid:
			emails.append(str(primary).strip())

		if email_column2 and email_column2 in data.columns:
			secondary = row.get(email_column2)
			secondary_valid = secondary is not None and _valid_email(secondary)
			if secondary_valid:
				sec = str(secondary).strip()
				if sec not in emails:
					emails.append(sec)

		# collect rows that contain email-like values but are invalid
		raw_primary = str(primary).strip() if primary is not None else ""
		raw_secondary = str(row.get(email_column2, "")).strip() if email_column2 and email_column2 in data.columns else ""
		primary_present = bool(raw_primary)
		secondary_present = bool(raw_secondary)
		invalid_present = (primary_present and not primary_valid) or (secondary_present and not secondary_valid)
		if invalid_present:
			invalid_rows.append({
				"row_index": int(idx) + 1,
				"customer_id": raw_id,
				"email_1": raw_primary,
				"email_2": raw_secondary,
			})

		if emails:
			for email in emails:
				norm_email = email.strip().lower()
				if norm_email in mapping_seen[raw_id]:
					continue
				mapping_seen[raw_id].add(norm_email)
				mapping_lists[raw_id].append(email.strip())

	if invalid_rows:
		print(f"[WARN] Nalezeny nevalidni e-maily v {len(invalid_rows)} radcich excelu ({excel_path}):")
		for item in invalid_rows[:20]:
			print(
				f"[WARN] Row {item['row_index']}: Customer {item['customer_id']} - email_1='{item['email_1']}' email_2='{item['email_2']}'"
			)
		if len(invalid_rows) > 20:
			print(f"[WARN] ... a dalsich {len(invalid_rows)-20} zaznamu")

	return {
		customer_id: ", ".join(emails)
		for customer_id, emails in mapping_lists.items()
		if emails
	}


def extract_customer_id(filename_without_ext: str, pattern: str | None) -> str | None:
	if pattern:
		match = re.search(pattern, filename_without_ext)
		if not match:
			return None
		if match.groups():
			return match.group(1).strip()
		return match.group(0).strip()

	digits = re.search(r"\d+", filename_without_ext)
	if digits:
		return digits.group(0)

	cleaned = filename_without_ext.strip()
	return cleaned if cleaned else None


def extract_customer_id_from_filename_start(filename_without_ext: str) -> str | None:
	match = re.match(r"^\s*([A-Za-z0-9]+)", filename_without_ext)
	if not match:
		return None
	value = _canonical_customer_id(match.group(1).strip())
	return value if value else None


def _canonical_customer_id(value: str | None) -> str:
	if not value:
		return ""
	cleaned = str(value).strip()
	cleaned = re.sub(r"\.0+$", "", cleaned)
	return cleaned


def _normalize_customer_id(value: str | None) -> str:
	if not value:
		return ""
	normalized = str(value).strip().lower().replace(" ", "")
	normalized = re.sub(r"\.0+$", "", normalized)
	return normalized


def extract_bill_to_customer_id(pdf_content: bytes) -> str | None:
	try:
		from pypdf import PdfReader
	except ImportError as error:
		raise RuntimeError(
			"Chybi knihovna 'pypdf'. Nainstalujte ji prikazem: pip install pypdf"
		) from error

	reader = PdfReader(io.BytesIO(pdf_content))
	text_parts: list[str] = []
	for page in reader.pages:
		text_parts.append(page.extract_text() or "")
	text = "\n".join(text_parts)

	match = re.search(r"Bill\s*To\s*[:#]?\s*([A-Za-z0-9]+)", text, flags=re.IGNORECASE)
	if not match:
		return None
	value = match.group(1).strip()
	value = re.sub(r"\.0+$", "", value)
	return value if value else None


def _parse_recipient_list(raw: str | None) -> list[str]:
	"""Parse a raw recipient string (comma/semicolon separated) into list of addresses."""
	if not raw:
		return []
	parts = re.split(r"[;,]", raw)
	return [p.strip() for p in parts if p and p.strip()]


def load_skip_bill_to_prefixes(
	skip_excel_path: Path = Path("inputs/skip.xlsx"),
	bill_to_column: str = "Bill-To",
) -> tuple[str, ...]:
	if not skip_excel_path.exists():
		print(f"[INFO] Skip soubor nenalezen: {skip_excel_path}. Filtr Bill-To nebude pouzit.")
		return tuple()

	data = pd.read_excel(skip_excel_path, dtype=str)
	if bill_to_column not in data.columns:
		print(
			f"[WARN] Skip soubor {skip_excel_path} neobsahuje sloupec '{bill_to_column}'. Filtr Bill-To nebude pouzit."
		)
		return tuple()

	prefixes: set[str] = set()
	for raw_value in data[bill_to_column].dropna().tolist():
		value = str(raw_value).strip()
		if not value:
			continue
		value = re.sub(r"\.0+$", "", value)
		prefixes.add(value)

	ordered = tuple(sorted(prefixes, key=len, reverse=True))
	print(f"[INFO] Nacteno {len(ordered)} Bill-To prefixu pro skip z: {skip_excel_path}")
	return ordered


def _match_prefix(value: str, prefixes: tuple[str, ...]) -> str | None:
	for prefix in prefixes:
		if value.startswith(prefix):
			return prefix
	return None


def resolve_statements_source_folder_path(
	graph: GraphClient,
	drive_id: str,
	base_folder_path: str,
	prefix: str = "Statements of the account",
) -> str:
	children = graph.list_children_in_folder(drive_id, base_folder_path)
	prefix_lower = prefix.lower()
	candidates = [
		item
		for item in children
		if item.get("folder") and str(item.get("name", "")).lower().startswith(prefix_lower)
	]
	if not candidates:
		raise ValueError(
			f"Ve slozce '{base_folder_path}' nebyla nalezena podslozka zacinajici na '{prefix}'."
		)

	def _sort_key(item: dict) -> tuple[str, str]:
		return (
			str(item.get("lastModifiedDateTime", "")),
			str(item.get("name", "")),
		)

	selected = sorted(candidates, key=_sort_key, reverse=True)[0]
	selected_name = str(selected.get("name", "")).strip()
	if not selected_name:
		raise ValueError("Nalezena Statements slozka bez nazvu.")

	return f"{base_folder_path.strip('/')}/{selected_name}".strip("/")


def send_pdf_email(
	smtp_host: str,
	smtp_port: int,
	smtp_username: str,
	smtp_password: str,
	smtp_use_tls: bool,
	sender: str,
	recipient: list[str],
	bcc: list[str] | None,
	subject: str,
	body: str,
	attachment_name: str,
	attachment_content: bytes,
) -> None:
	bcc = bcc or []
	all_recipients = list(recipient)
	for addr in bcc:
		if addr and addr not in all_recipients:
			all_recipients.append(addr)

	message = EmailMessage()
	message["From"] = sender
	# set header to a comma-separated string but pass explicit recipient list to SMTP
	message["To"] = ", ".join(recipient)
	message["Subject"] = subject
	message.set_content(body)
	message.add_attachment(
		attachment_content,
		maintype="application",
		subtype="pdf",
		filename=attachment_name,
	)

	with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
		if smtp_use_tls:
			server.starttls()
		if smtp_username or smtp_password:
			server.login(smtp_username, smtp_password)
		server.send_message(message, to_addrs=all_recipients)


def run() -> int:
	load_dotenv()
	settings = Settings.from_env()

	print("[INFO] Nacitam mapu ID -> email z Excelu...")
	customer_email_map = load_customer_email_map(
		settings.mapping_excel_path,
		settings.mapping_id_column,
		settings.mapping_email_column,
		settings.mapping_email_column2,
	)
	print(f"[INFO] Nacteno {len(customer_email_map)} zaznamu.")
	if settings.test_mode:
		print(f"[INFO] TEST_MODE=ON, vsechny emaily budou odeslany na: {settings.test_recipient_email}")
	else:
		print("[INFO] TEST_MODE=OFF, emaily budou odeslany na zakaznicke adresy z Excelu.")
		if settings.production_bcc:
			print(f"[INFO] BCC v ostrem rezimu: {settings.production_bcc}")

	graph = GraphClient(settings)
	site_id = graph.get_site_id(settings.site_hostname, settings.site_path)
	drive_id = graph.resolve_drive_id(site_id, settings.drive_id, settings.drive_name)

	sent_folder_id = settings.sent_folder_id
	if sent_folder_id:
		try:
			graph.validate_folder_id(drive_id, sent_folder_id)
		except Exception:
			if settings.sent_folder_path:
				print("[WARN] SHAREPOINT_SENT_FOLDER_ID je neplatne, prechazim na SHAREPOINT_SENT_FOLDER_PATH.")
				sent_folder_id = graph.ensure_folder_path(drive_id, settings.sent_folder_path)
			else:
				raise
	else:
		if not settings.sent_folder_path:
			raise ValueError(
				"Chybi cilova slozka sent. Nastav SHAREPOINT_SENT_FOLDER_ID nebo SHAREPOINT_SENT_FOLDER_PATH."
			)
		sent_folder_id = graph.ensure_folder_path(drive_id, settings.sent_folder_path)

	skipped_folder_path = f"{settings.source_folder_path}/skipped"
	skipped_folder_id = graph.ensure_folder_path(drive_id, skipped_folder_path)
	redo_folder_path = f"{settings.source_folder_path}/redo"
	redo_folder_id = graph.ensure_folder_path(drive_id, redo_folder_path)
	redo_error_folder_path = f"{settings.source_folder_path}/redo/error"
	redo_error_folder_id = graph.ensure_folder_path(drive_id, redo_error_folder_path)

	state = ProcessingState(settings.state_db_path)
	processing_source_folder_path = resolve_statements_source_folder_path(
		graph,
		drive_id,
		settings.source_folder_path,
	)
	print(f"[INFO] Zdrojova Statements slozka pro davku: {processing_source_folder_path}")

	print("[INFO] Nacitam PDF soubory ze SharePoint slozky...")
	pdf_items = graph.list_pdfs_in_folder(drive_id, processing_source_folder_path)
	print(f"[INFO] Nalezeno {len(pdf_items)} PDF souboru.")
	skip_bill_to_prefixes = load_skip_bill_to_prefixes()

	# seed processing state for currently visible source items
	for item in pdf_items:
		state.ensure_exists(
			item_id=item["id"],
			file_name=item["name"],
			customer_id=None,
			customer_email=None,
			target_recipient=None,
		)

	items_by_id = {str(item["id"]): item for item in pdf_items}
	queue_item_ids = state.next_batch_item_ids(list(items_by_id.keys()), settings.batch_size)
	pdf_items = [items_by_id[item_id] for item_id in queue_item_ids if item_id in items_by_id]
	print(f"[INFO] Davka ke zpracovani: {len(pdf_items)} / {len(items_by_id)} (BATCH_SIZE={settings.batch_size})")
	
	# Export queue before processing starts
	try:
		state.export_queue_report(queue_item_ids)
		print(f"[INFO] Exportovano seznam k zpracovani: {EXPORT_DIR / '_queue.xlsx'}")
	except Exception as ex_queue:
		print(f"[WARN] Nepodarilo se ulozit {EXPORT_DIR / '_queue.xlsx'}: {ex_queue}")

	sent = 0
	skipped = 0
	errors = 0

	try:
		def move_to_redo(current_item_id: str, current_file_name: str, reason: str, error_bucket: bool = False) -> None:
			state.mark_status(current_item_id, "failed", reason)
			try:
				target_folder_id = redo_error_folder_id if error_bucket else redo_folder_id
				graph.copy_item_to_folder(drive_id, current_item_id, target_folder_id, current_file_name)
				state.mark_moved_to_redo(current_item_id, reason)
				if error_bucket:
					print(f"[OK] Zkopirovano do redo/error: {current_file_name}")
				else:
					print(f"[OK] Zkopirovano do redo: {current_file_name}")
			except Exception as move_err:
				print(f"[ERROR] Nelze zkopirovat do redo: {move_err}")
			print(f"[ERROR] Soubor {current_file_name}: {reason}")

		for item in pdf_items:
			file_name = item["name"]
			item_id = item["id"]
			stem = Path(file_name).stem
			skip_prefix = _match_prefix(stem, skip_bill_to_prefixes)
			if skip_prefix:
				state.ensure_exists(
					item_id=item_id,
					file_name=file_name,
					customer_id=None,
					customer_email=None,
					target_recipient=None,
				)
				state.mark_status(item_id, "skipped_bill_to")
				graph.copy_item_to_folder(drive_id, item_id, skipped_folder_id, file_name)
				state.mark_moved_to_skipped(item_id)
				print(
					f"[SKIP] Soubor {file_name}: zacina Bill-To '{skip_prefix}' ze skip.xlsx, nebude odeslan."
				)
				print(f"[OK] Zkopirovano do skipped bez odeslani: {file_name}")
				skipped += 1
				continue
			customer_id = extract_customer_id_from_filename_start(stem)

			if not customer_id:
				state.ensure_exists(
					item_id=item_id,
					file_name=file_name,
					customer_id=None,
					customer_email=None,
					target_recipient=None,
				)
				move_to_redo(item_id, file_name, "Nelze vycist customer ID z nazvu souboru")
				skipped += 1
				continue

			customer_email = customer_email_map.get(_canonical_customer_id(customer_id))
			if not customer_email:
				state.ensure_exists(
					item_id=item_id,
					file_name=file_name,
					customer_id=customer_id,
					customer_email=None,
					target_recipient=None,
				)
				move_to_redo(item_id, file_name, f"Pro customer ID {customer_id} neni email v Excelu")
				skipped += 1
				continue

			raw_recipient = settings.test_recipient_email if settings.test_mode else customer_email
			recipient_list = _parse_recipient_list(raw_recipient)
			bcc_list = [] if settings.test_mode else _parse_recipient_list(settings.production_bcc)
			body = settings.email_body_template.format(
				customer_id=customer_id,
				file_name=file_name,
				customer_email=customer_email,
			)
			if settings.test_mode:
				body = (
					f"{body}\n\n"
					f"[TEST MODE] Skutecny zakaznicky email z Excelu: {customer_email}\n"
					f"[TEST MODE] Odeslano pouze na: {', '.join(recipient_list)}"
				)

			state.ensure_exists(
				item_id=item_id,
				file_name=file_name,
				customer_id=customer_id,
				customer_email=customer_email,
				target_recipient=(
					", ".join(recipient_list)
					if not bcc_list
					else f"{', '.join(recipient_list)} (bcc: {', '.join(bcc_list)})"
				),
			)

			record = state.get(item_id)
			if record and record["moved_to_sent"] == 1:
				print(f"[SKIP] Jiz zpracovano (kopie v sent uz existuje): {file_name}")
				skipped += 1
				continue

			try:
				if not record or record["email_sent"] == 0:
					state.mark_status(item_id, "sending")
					pdf_content = graph.download_file(drive_id, item_id)
					bill_to_customer_id = extract_bill_to_customer_id(pdf_content)
					if not bill_to_customer_id:
						move_to_redo(
							item_id,
							file_name,
							"Nelze nacist 'Bill To' customer ID z PDF",
							error_bucket=True,
						)
						errors += 1
						continue

					if _normalize_customer_id(customer_id) != _normalize_customer_id(bill_to_customer_id):
						move_to_redo(
							item_id,
							file_name,
							f"Neshoda customer ID: filename='{customer_id}' vs Bill-To='{bill_to_customer_id}'",
							error_bucket=True,
						)
						errors += 1
						continue
					subject = settings.email_subject_template.format(
						customer_id=customer_id,
						file_name=file_name,
					)

					send_pdf_email(
						smtp_host=settings.smtp_host,
						smtp_port=settings.smtp_port,
						smtp_username=settings.smtp_username,
						smtp_password=settings.smtp_password,
						smtp_use_tls=settings.smtp_use_tls,
						sender=settings.email_from,
						recipient=recipient_list,
						bcc=bcc_list,
						subject=subject,
						body=body,
						attachment_name=file_name,
						attachment_content=pdf_content,
					)
					state.mark_email_sent(item_id)
					print(f"[OK] Odeslano: {file_name} -> {', '.join(recipient_list)}")
					sent += 1

				state.mark_status(item_id, "moving")
				graph.copy_item_to_folder(drive_id, item_id, sent_folder_id, file_name)
				state.mark_moved(item_id)
				print(f"[OK] Zkopirovano do sent: {file_name}")
			except Exception as file_error:
				move_to_redo(item_id, file_name, str(file_error), error_bucket=True)
				errors += 1
	finally:
		try:
			state.export_to_excel()
			sent_report_count = state.export_sent_report()
			failed_report_count = state.export_failed_report()
			print(
				f"[INFO] Exportovano: {EXPORT_DIR / '_log.xlsx'}, {EXPORT_DIR / '_sent_report.xlsx'} "
				f"({sent_report_count} docs), {EXPORT_DIR / '_failed_report.xlsx'} ({failed_report_count} docs)"
			)
		except Exception as ex_export:
			print(f"[WARN] Nepodarilo se ulozit reporty: {ex_export}")
		state.close()

	print("=" * 70)
	print(f"[DONE] Odeslano: {sent}, Preskoceno: {skipped}, Chyby: {errors}")
	print(f"[DONE] Celkem zpracovano: {sent + skipped + errors} dokumentu")
	print("=" * 70)
	return 0 if errors == 0 else 1


if __name__ == "__main__":
	try:
		raise SystemExit(run())
	except Exception as error:
		print(f"[ERROR] {error}", file=sys.stderr)
		raise SystemExit(1)
