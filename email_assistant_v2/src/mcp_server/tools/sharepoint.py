from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import msal
import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# --- Modul-level stav inicializovany pres sharepoint_initialize ---
_graph: "_GraphClient | None" = None
_drive_id: str | None = None
_sent_folder_id: str | None = None
_redo_folder_id: str | None = None
_redo_error_folder_id: str | None = None
_skipped_folder_id: str | None = None
_source_folder_path: str | None = None


def _get_graph() -> "_GraphClient":
    if _graph is None:
        raise RuntimeError("SharePoint neni inicializovan. Zavolej sharepoint_initialize nejdrive.")
    return _graph


def _folder_id(destination: str) -> str:
    mapping = {
        "sent": _sent_folder_id,
        "redo": _redo_folder_id,
        "redo_error": _redo_error_folder_id,
        "skipped": _skipped_folder_id,
    }
    folder_id = mapping.get(destination)
    if not folder_id:
        raise ValueError(f"Neznamy cil '{destination}' nebo neinicialized. Platne hodnoty: {list(mapping.keys())}")
    return folder_id


# ============================================================
# GraphClient - kopirovan a zjednodussen z email_assistant
# ============================================================

class _GraphClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        self._app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret
        )
        self._scope = ["https://graph.microsoft.com/.default"]

    def _token(self) -> str:
        result = self._app.acquire_token_silent(self._scope, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=self._scope)
        token = result.get("access_token")
        if not token:
            raise RuntimeError(f"Nelze ziskat access token: {result.get('error_description', result)}")
        return token

    def _req(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        resp = requests.request(method, url, headers=headers, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp

    def get_site_id(self, hostname: str, site_path: str) -> str:
        normalized = site_path if site_path.startswith("/") else f"/{site_path}"
        return self._req("GET", f"{GRAPH_BASE_URL}/sites/{hostname}:{normalized}").json()["id"]

    def resolve_drive_id(self, site_id: str, drive_id: str | None, drive_name: str | None) -> str:
        if drive_id:
            return drive_id
        if not drive_name:
            raise ValueError("Neni nastaveno SHAREPOINT_DRIVE_ID ani SHAREPOINT_DRIVE_NAME")
        drives = self._req("GET", f"{GRAPH_BASE_URL}/sites/{site_id}/drives").json().get("value", [])
        for drive in drives:
            if drive.get("name") == drive_name:
                return drive["id"]
        raise ValueError(f"Drive '{drive_name}' nenalezen")

    def resolve_folder_id(self, drive_id: str, folder_path: str) -> str:
        variants = _folder_path_variants(folder_path)
        last_error = None
        for variant in variants:
            url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{variant}"
            try:
                payload = self._req("GET", url).json()
                if not payload.get("folder"):
                    raise ValueError(f"Cesta neni slozka: {folder_path}")
                return payload["id"]
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    last_error = e
                    continue
                raise
        if last_error:
            raise last_error
        raise ValueError(f"Slozka nenalezena: {folder_path}")

    def ensure_folder_path(self, drive_id: str, folder_path: str) -> str:
        try:
            return self.resolve_folder_id(drive_id, folder_path)
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
        cleaned = folder_path.strip("/")
        if not cleaned or "/" not in cleaned:
            raise
        parent_path, folder_name = cleaned.rsplit("/", 1)
        parent_id = self.resolve_folder_id(drive_id, parent_path)
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{parent_id}/children"
        payload = {"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"}
        return self._req("POST", url, json=payload).json()["id"]

    def list_pdfs(self, drive_id: str, folder_path: str) -> list[dict]:
        variants = _folder_path_variants(folder_path)
        last_error = None
        for variant in variants:
            url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{variant}:/children"
            try:
                items = self._req("GET", url, params={"$top": "999"}).json().get("value", [])
                return [i for i in items if i.get("file") and i.get("name", "").lower().endswith(".pdf")]
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    last_error = e
                    continue
                raise
        if last_error:
            raise last_error
        raise ValueError(f"Slozka nenalezena: {folder_path}")

    def list_children(self, drive_id: str, folder_path: str) -> list[dict]:
        variants = _folder_path_variants(folder_path)
        last_error = None
        for variant in variants:
            url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{variant}:/children"
            try:
                return self._req("GET", url, params={"$top": "999"}).json().get("value", [])
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    last_error = e
                    continue
                raise
        if last_error:
            raise last_error
        raise ValueError(f"Slozka nenalezena: {folder_path}")

    def download_file(self, drive_id: str, item_id: str) -> bytes:
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content"
        return self._req("GET", url).content

    def upload_file(self, drive_id: str, folder_id: str, file_name: str, content: bytes) -> None:
        escaped = quote(file_name, safe="")
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{folder_id}:/{escaped}:/content"
        self._req("PUT", url, headers={"Content-Type": "application/pdf"}, data=content)

    def copy_file(self, drive_id: str, item_id: str, target_folder_id: str, file_name: str) -> None:
        content = self.download_file(drive_id, item_id)
        self.upload_file(drive_id, target_folder_id, file_name, content)


# ============================================================
# Pomocne funkce
# ============================================================

def _folder_path_variants(folder_path: str) -> list[str]:
    cleaned = folder_path.strip().strip("/")
    if not cleaned:
        return []
    variants = [cleaned]
    prefix = "Shared Documents/"
    if cleaned.startswith(prefix):
        variants.append(cleaned[len(prefix):])
    if cleaned == "Shared Documents":
        variants.append("")
    return list(dict.fromkeys(variants))


def _split_site_url(site_url: str) -> tuple[str, str]:
    parsed = urlparse(site_url)
    if not parsed.scheme or not parsed.netloc or not parsed.path:
        raise ValueError("Neplatna hodnota SHAREPOINT_SITE_URL")
    return parsed.netloc, parsed.path


def _normalize_folder_path(raw: str, site_path: str) -> str:
    folder = raw.strip()
    if not folder:
        raise ValueError("Prazdna cesta slozky")
    if folder.startswith("http://") or folder.startswith("https://"):
        parsed = urlparse(folder)
        query = parse_qs(parsed.query)
        folder = unquote(query["id"][0]) if "id" in query and query["id"] else unquote(parsed.path)
    normalized_site = site_path if site_path.startswith("/") else f"/{site_path}"
    if folder.startswith(normalized_site):
        folder = folder[len(normalized_site):]
    folder = folder.lstrip("/")
    if not folder:
        raise ValueError("Nelze odvodit cestu slozky")
    return folder


def _resolve_statements_folder(graph: _GraphClient, drive_id: str, base_folder_path: str, prefix: str = "Statements of the account") -> str:
    children = graph.list_children(drive_id, base_folder_path)
    prefix_lower = prefix.lower()
    candidates = [
        c for c in children
        if c.get("folder") and str(c.get("name", "")).lower().startswith(prefix_lower)
    ]
    if not candidates:
        raise ValueError(f"Ve slozce '{base_folder_path}' nenalezena podslozka zacinajici na '{prefix}'")
    selected = sorted(candidates, key=lambda x: (str(x.get("lastModifiedDateTime", "")), str(x.get("name", ""))), reverse=True)[0]
    name = str(selected.get("name", "")).strip()
    if not name:
        raise ValueError("Nalezena Statements slozka bez nazvu")
    return f"{base_folder_path.strip('/')}/{name}".strip("/")


# ============================================================
# MCP Tool funkce
# ============================================================

def sharepoint_initialize() -> str:
    """
    Inicializuje SharePoint pripojeni: autentifikace, drive, slozky.
    Musi byt zavolano pred ostatnimi sharepoint_ nastroji.
    Vraci JSON s drive_id, folder IDs a zdrojovou cestou.
    """
    global _graph, _drive_id, _sent_folder_id, _redo_folder_id
    global _redo_error_folder_id, _skipped_folder_id, _source_folder_path

    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]

    site_url = os.getenv("SHAREPOINT_SITE_URL")
    if site_url:
        site_hostname, site_path = _split_site_url(site_url)
    else:
        site_hostname = os.environ["SHAREPOINT_SITE_HOSTNAME"]
        site_path = os.environ["SHAREPOINT_SITE_PATH"]

    raw_source = os.getenv("SHAREPOINT_FOLDER_PATH") or os.environ["SP_SOURCE_FOLDER_PATH"]
    source_base = _normalize_folder_path(raw_source, site_path)

    raw_sent = os.getenv("SHAREPOINT_SENT_FOLDER_PATH") or os.getenv("SP_SENT_FOLDER_PATH")
    sent_path = _normalize_folder_path(raw_sent, site_path) if raw_sent else None

    drive_id_env = os.getenv("SHAREPOINT_DRIVE_ID") or os.getenv("SP_DRIVE_ID")
    drive_name = os.getenv("SHAREPOINT_DRIVE_NAME") or os.getenv("SP_DRIVE_NAME")

    graph = _GraphClient(tenant_id, client_id, client_secret)
    site_id = graph.get_site_id(site_hostname, site_path)
    drive_id = graph.resolve_drive_id(site_id, drive_id_env, drive_name)

    # Zdrojova slozka (latest Statements subfolder)
    source_folder = _resolve_statements_folder(graph, drive_id, source_base)

    # Sent slozka
    sent_id: str
    sent_folder_id_env = os.getenv("SHAREPOINT_SENT_FOLDER_ID") or os.getenv("SP_SENT_FOLDER_ID")
    if sent_folder_id_env:
        sent_id = sent_folder_id_env
    elif sent_path:
        sent_id = graph.ensure_folder_path(drive_id, sent_path)
    else:
        raise ValueError("Neni nastavena sent slozka (SHAREPOINT_SENT_FOLDER_PATH nebo SHAREPOINT_SENT_FOLDER_ID)")

    redo_path = f"{source_base}/redo"
    redo_error_path = f"{source_base}/redo/error"
    skipped_path = f"{source_base}/skipped"

    redo_id = graph.ensure_folder_path(drive_id, redo_path)
    redo_error_id = graph.ensure_folder_path(drive_id, redo_error_path)
    skipped_id = graph.ensure_folder_path(drive_id, skipped_path)

    # Uloz stav
    _graph = graph
    _drive_id = drive_id
    _sent_folder_id = sent_id
    _redo_folder_id = redo_id
    _redo_error_folder_id = redo_error_id
    _skipped_folder_id = skipped_id
    _source_folder_path = source_folder

    return json.dumps({
        "drive_id": drive_id,
        "sent_folder_id": sent_id,
        "redo_folder_id": redo_id,
        "redo_error_folder_id": redo_error_id,
        "skipped_folder_id": skipped_id,
        "source_folder_path": source_folder,
    })


def sharepoint_list_pdfs() -> str:
    """
    Vrati seznam PDF souboru ze zdrojove SharePoint slozky.
    Vraci JSON pole objektu [{id, name}].
    """
    graph = _get_graph()
    if not _drive_id or not _source_folder_path:
        raise RuntimeError("SharePoint neni inicializovan")
    items = graph.list_pdfs(_drive_id, _source_folder_path)
    return json.dumps([{"id": i["id"], "name": i["name"]} for i in items])


def sharepoint_download_pdf(item_id: str) -> str:
    """
    Stahne PDF soubor z SharePointu.
    Vraci obsah souboru jako base64 retezec.
    """
    graph = _get_graph()
    if not _drive_id:
        raise RuntimeError("SharePoint neni inicializovan")
    content = graph.download_file(_drive_id, item_id)
    return base64.b64encode(content).decode("utf-8")


def sharepoint_copy_file(item_id: str, destination: str, file_name: str) -> str:
    """
    Zkopiruje soubor do cilove slozky.
    destination: 'sent' | 'redo' | 'redo_error' | 'skipped'
    Vraci 'OK' nebo chybovou zpravu.
    """
    graph = _get_graph()
    if not _drive_id:
        raise RuntimeError("SharePoint neni inicializovan")
    target_id = _folder_id(destination)
    graph.copy_file(_drive_id, item_id, target_id, file_name)
    return "OK"
