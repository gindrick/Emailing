"""
DatabaseAgent - specializovany agent pro SQLite operace.

Zodpovednost:
- Inicializace databaze
- Vkladani a aktualizace zaznamu o PDF souborech
- Nacteni davky k zpracovani
- Aktualizace stavu souboru (pending/sending/email_sent/completed/redo/skipped)
- Export reportu do Excel
- Nacteni souhrnnych statistik

Povolene nastroje (12): vsechny db_* nastroje
"""

from __future__ import annotations

import json
import logging

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DatabaseAgent(BaseAgent):
    """Agent pro vsechny databazove operace (SQLite pres MCP server)."""

    TOOL_WHITELIST = [
        "db_initialize",
        "db_seed_items",
        "db_get_batch",
        "db_get_file_state",
        "db_ensure_file",
        "db_mark_status",
        "db_mark_email_sent",
        "db_mark_moved",
        "db_mark_redo",
        "db_mark_skipped",
        "db_export_reports",
        "db_get_summary",
    ]

    async def initialize(self) -> str:
        """Inicializuje SQLite databazi (vytvori tabulku pokud neexistuje)."""
        result = await self.call_tool("db_initialize")
        logger.info(f"  [DatabaseAgent] DB inicializovana: {result}")
        return result

    async def seed_items(self, items: list[dict]) -> str:
        """
        Vlozi nebo aktualizuje zaznamy PDF souboru v DB.
        items: [{id, name}]
        Vraci pocet zpracovanych zaznamu.
        """
        items_json = json.dumps(items)
        result = await self.call_tool("db_seed_items", {"items_json": items_json})
        logger.info(f"  [DatabaseAgent] Zaznamu vlozeno/aktualizovano: {result}")
        return result

    async def get_batch(self, item_ids: list[str]) -> list[str]:
        """
        Vrati seznam item_id k zpracovani (filtrovan dle BATCH_SIZE a stavu).
        Vraci list item_id.
        """
        item_ids_json = json.dumps(item_ids)
        result = await self.call_tool("db_get_batch", {"item_ids_json": item_ids_json})
        batch = json.loads(result)
        logger.info(f"  [DatabaseAgent] Davka k zpracovani: {len(batch)} zaznamu")
        return batch

    async def get_file_state(self, item_id: str) -> dict:
        """Vrati aktualni stav zpracovani souboru jako dict."""
        result = await self.call_tool("db_get_file_state", {"item_id": item_id})
        return json.loads(result) or {}

    async def ensure_file(
        self,
        item_id: str,
        file_name: str,
        customer_id: str,
        customer_email: str,
        target_recipient: str,
    ) -> str:
        """Ulozi nebo aktualizuje metadata souboru v DB."""
        return await self.call_tool("db_ensure_file", {
            "item_id": item_id,
            "file_name": file_name,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "target_recipient": target_recipient,
        })

    async def mark_status(self, item_id: str, status: str, error_message: str = "") -> str:
        """Nastavi status zaznamu v DB."""
        return await self.call_tool("db_mark_status", {
            "item_id": item_id,
            "status": status,
            "error_message": error_message,
        })

    async def mark_email_sent(self, item_id: str) -> str:
        """Oznaci email jako odeslany."""
        return await self.call_tool("db_mark_email_sent", {"item_id": item_id})

    async def mark_moved(self, item_id: str) -> str:
        """Oznaci soubor jako presunuty do sent (dokonceno)."""
        return await self.call_tool("db_mark_moved", {"item_id": item_id})

    async def mark_redo(self, item_id: str, error_message: str = "") -> str:
        """Oznaci soubor pro opakovani (redo slozka)."""
        return await self.call_tool("db_mark_redo", {
            "item_id": item_id,
            "error_message": error_message,
        })

    async def mark_skipped(self, item_id: str) -> str:
        """Oznaci soubor jako preskoceny."""
        return await self.call_tool("db_mark_skipped", {"item_id": item_id})

    async def export_reports(self) -> str:
        """Exportuje reporty do Excel souboru v output/ slozce."""
        result = await self.call_tool("db_export_reports")
        logger.info(f"  [DatabaseAgent] Export reportu: {result}")
        return result

    async def get_summary(self) -> dict:
        """Vrati souhrnne statistiky zpracovani jako dict."""
        result = await self.call_tool("db_get_summary")
        return json.loads(result)
