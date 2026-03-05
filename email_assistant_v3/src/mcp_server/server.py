"""
MCP Server pro email_assistant_v2
Poskytuje nastroje pro SharePoint, Excel, SQLite, PDF a SMTP.
Spusteni: uv run python src/mcp_server/server.py
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Dict, Optional

import uvicorn
from mcp.server.lowlevel import Server
import mcp.types as types
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from tools.sharepoint import (
    sharepoint_initialize,
    sharepoint_list_pdfs,
    sharepoint_download_pdf,
    sharepoint_copy_file,
)
from tools.excel_tools import (
    excel_load_customer_mapping,
    excel_load_skip_prefixes,
)
from tools.database import (
    db_initialize,
    db_seed_items,
    db_get_batch,
    db_get_file_state,
    db_ensure_file,
    db_mark_status,
    db_mark_email_sent,
    db_mark_moved,
    db_mark_redo,
    db_mark_skipped,
    db_export_reports,
    db_get_summary,
)
from tools.pdf_tools import pdf_extract_text
from tools.email_sender import smtp_send_email, smtp_send_plain_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

server = Server("email-assistant-mcp-server")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="sharepoint_initialize",
            description="Inicializuje SharePoint pripojeni, drive a vsechny slozky (sent, redo, skipped). Musi byt zavolano jako prvni. Vraci JSON s drive_id a folder IDs.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="sharepoint_list_pdfs",
            description="Vrati seznam PDF souboru ze zdrojove SharePoint slozky (nejnovejsi Statements subfolder). Vraci JSON pole [{id, name}].",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="sharepoint_download_pdf",
            description="Stahne PDF soubor ze SharePointu. Vraci obsah jako base64 retezec.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "SharePoint item ID souboru"},
                },
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="sharepoint_copy_file",
            description="Zkopiruje soubor do cilove SharePoint slozky. destination: 'sent' | 'redo' | 'redo_error' | 'skipped'. Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "SharePoint item ID"},
                    "destination": {"type": "string", "description": "Cil: sent | redo | redo_error | skipped"},
                    "file_name": {"type": "string", "description": "Nazev souboru"},
                },
                "required": ["item_id", "destination", "file_name"],
            },
        ),
        types.Tool(
            name="excel_load_customer_mapping",
            description="Nacte mapovani customer_id -> emaily z Excel souboru. Vraci JSON objekt {customer_id: 'email1, email2'}.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="excel_load_skip_prefixes",
            description="Nacte seznam Bill-To prefixu pro preskoceni z inputs/skip.xlsx. Vraci JSON pole retezcu.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="db_initialize",
            description="Inicializuje SQLite databazi pro sledovani zpracovani. Musi byt zavolano pred ostatnimi db_ nastroji.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="db_seed_items",
            description="Vlozi nebo updatuje zaznamy PDF souboru v DB. items_json: JSON pole [{id, name}]. Vraci pocet zpracovanych.",
            inputSchema={
                "type": "object",
                "properties": {
                    "items_json": {"type": "string", "description": "JSON pole [{id, name}]"},
                },
                "required": ["items_json"],
            },
        ),
        types.Tool(
            name="db_get_batch",
            description="Vrati seznam item_id k zpracovani v ramci BATCH_SIZE. item_ids_json: JSON pole vsech nalezenych ID. Vraci JSON pole ID k zpracovani.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_ids_json": {"type": "string", "description": "JSON pole item ID"},
                },
                "required": ["item_ids_json"],
            },
        ),
        types.Tool(
            name="db_get_file_state",
            description="Vrati aktualni stav zpracovani souboru jako JSON.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                },
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="db_ensure_file",
            description="Ulozi nebo updatuje metadata souboru v DB. Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "file_name": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "customer_email": {"type": "string"},
                    "target_recipient": {"type": "string"},
                },
                "required": ["item_id", "file_name", "customer_id", "customer_email", "target_recipient"],
            },
        ),
        types.Tool(
            name="db_mark_status",
            description="Nastavi status zaznamu v DB. Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "status": {"type": "string", "description": "Napr: pending, sending, moving, failed, completed"},
                    "error_message": {"type": "string", "default": ""},
                },
                "required": ["item_id", "status"],
            },
        ),
        types.Tool(
            name="db_mark_email_sent",
            description="Oznaci email jako odeslany v DB. Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="db_mark_moved",
            description="Oznaci soubor jako presunuty do sent (dokonceno). Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="db_mark_redo",
            description="Oznaci soubor pro opakovanje (redo slozka). Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "error_message": {"type": "string", "default": ""},
                },
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="db_mark_skipped",
            description="Oznaci soubor jako preskoceny (skipped). Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="db_export_reports",
            description="Exportuje reporty do Excel souboru v output/ slozce. Vraci prehled exportovanych souboru.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="pdf_extract_text",
            description="Extrahuje text z PDF dokumentu (base64 vstup). Vraci plain text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_b64": {"type": "string", "description": "Obsah PDF zakodovany v base64"},
                },
                "required": ["pdf_b64"],
            },
        ),
        types.Tool(
            name="smtp_send_email",
            description="Odesle email s PDF prilohou. to_recipients a bcc_recipients jsou emaily oddelene carkami. Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to_recipients": {"type": "string", "description": "Emaily oddelene carkou"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "pdf_b64": {"type": "string", "description": "PDF zakodovane v base64"},
                    "file_name": {"type": "string", "description": "Nazev prilohy"},
                    "bcc_recipients": {"type": "string", "default": "", "description": "BCC emaily oddelene carkou"},
                },
                "required": ["to_recipients", "subject", "body", "pdf_b64", "file_name"],
            },
        ),
        types.Tool(
            name="db_get_summary",
            description="Vrati souhrnne statistiky zpracovani z DB jako JSON: pocty completed/sent/redo/failed/skipped a seznam chybovych souboru.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="smtp_send_plain_email",
            description="Odesle plain-text email bez prilohy (napr. souhrnny report po zpracovani). Vraci 'OK'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to_recipients": {"type": "string", "description": "Emaily oddelene carkou"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to_recipients", "subject", "body"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Optional[Dict[str, Any]] = None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if arguments is None:
        arguments = {}

    try:
        result: str

        if name == "sharepoint_initialize":
            result = sharepoint_initialize()
        elif name == "sharepoint_list_pdfs":
            result = sharepoint_list_pdfs()
        elif name == "sharepoint_download_pdf":
            result = sharepoint_download_pdf(arguments["item_id"])
        elif name == "sharepoint_copy_file":
            result = sharepoint_copy_file(
                arguments["item_id"],
                arguments["destination"],
                arguments["file_name"],
            )
        elif name == "excel_load_customer_mapping":
            result = excel_load_customer_mapping()
        elif name == "excel_load_skip_prefixes":
            result = excel_load_skip_prefixes()
        elif name == "db_initialize":
            result = db_initialize()
        elif name == "db_seed_items":
            result = db_seed_items(arguments["items_json"])
        elif name == "db_get_batch":
            result = db_get_batch(arguments["item_ids_json"])
        elif name == "db_get_file_state":
            result = db_get_file_state(arguments["item_id"])
        elif name == "db_ensure_file":
            result = db_ensure_file(
                arguments["item_id"],
                arguments["file_name"],
                arguments.get("customer_id", ""),
                arguments.get("customer_email", ""),
                arguments.get("target_recipient", ""),
            )
        elif name == "db_mark_status":
            result = db_mark_status(
                arguments["item_id"],
                arguments["status"],
                arguments.get("error_message", ""),
            )
        elif name == "db_mark_email_sent":
            result = db_mark_email_sent(arguments["item_id"])
        elif name == "db_mark_moved":
            result = db_mark_moved(arguments["item_id"])
        elif name == "db_mark_redo":
            result = db_mark_redo(arguments["item_id"], arguments.get("error_message", ""))
        elif name == "db_mark_skipped":
            result = db_mark_skipped(arguments["item_id"])
        elif name == "db_export_reports":
            result = db_export_reports()
        elif name == "db_get_summary":
            result = db_get_summary()
        elif name == "smtp_send_plain_email":
            result = smtp_send_plain_email(
                to_recipients=arguments["to_recipients"],
                subject=arguments["subject"],
                body=arguments["body"],
            )
        elif name == "pdf_extract_text":
            result = pdf_extract_text(arguments["pdf_b64"])
        elif name == "smtp_send_email":
            result = smtp_send_email(
                to_recipients=arguments["to_recipients"],
                subject=arguments["subject"],
                body=arguments["body"],
                pdf_b64=arguments["pdf_b64"],
                file_name=arguments["file_name"],
                bcc_recipients=arguments.get("bcc_recipients", ""),
            )
        else:
            raise ValueError(f"Neznamy nastroj: {name}")

        return [types.TextContent(type="text", text=result)]

    except Exception as e:
        error_msg = f"[TOOL ERROR] {name}: {str(e)}"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=error_msg)]


# --- HTTP server setup ---

session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=True,
    event_store=None,
    stateless=True,
)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        logger.info("MCP Email Assistant server spusten na portu 8002")
        yield
        logger.info("MCP Email Assistant server zastaven")


starlette_app = Starlette(
    debug=False,
    routes=[Mount("/mcp", app=handle_streamable_http)],
    lifespan=lifespan,
)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.getenv("MCP_SERVER_PORT", "8002"))
    logger.info(f"Spoustim MCP server na portu {port}...")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
