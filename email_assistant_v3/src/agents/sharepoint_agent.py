"""
SharePointAgent - specializovany agent pro operace se SharePointem.

Zodpovednost:
- Inicializace SharePoint pripojeni (drive, slozky)
- Vylistovani PDF souboru ze zdrojove slozky
- Stazeni PDF souboru
- Kopirovani souboru do cilove slozky (sent/redo/redo_error/skipped)

Povolene nastroje (4): sharepoint_initialize, sharepoint_list_pdfs,
                        sharepoint_download_pdf, sharepoint_copy_file
"""

from __future__ import annotations

import json
import logging

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SharePointAgent(BaseAgent):
    """Agent pro vsechny SharePoint operace."""

    TOOL_WHITELIST = [
        "sharepoint_initialize",
        "sharepoint_list_pdfs",
        "sharepoint_download_pdf",
        "sharepoint_copy_file",
    ]

    async def initialize(self) -> dict:
        """
        Inicializuje SharePoint drive a vsechny pracovni slozky.
        Vraci dict s drive_id, folder IDs a source_folder_path.
        """
        result = await self.call_tool("sharepoint_initialize")
        info = json.loads(result)
        logger.info(f"  [SharePointAgent] Drive: {info.get('drive_id', '?')}")
        logger.info(f"  [SharePointAgent] Zdrojova slozka: {info.get('source_folder_path', '?')}")
        return info

    async def list_pdfs(self) -> list[dict]:
        """
        Vrati seznam PDF souboru ze zdrojove slozky.
        Vraci list[dict] ve formatu [{id, name}].
        """
        result = await self.call_tool("sharepoint_list_pdfs")
        items = json.loads(result)
        logger.info(f"  [SharePointAgent] Nalezeno PDF souboru: {len(items)}")
        return items

    async def download_pdf(self, item_id: str) -> str:
        """
        Stahne PDF soubor a vrati obsah jako base64 retezec.
        """
        logger.debug(f"  [SharePointAgent] Stahuji PDF item_id={item_id}")
        return await self.call_tool("sharepoint_download_pdf", {"item_id": item_id})

    async def copy_file(self, item_id: str, destination: str, file_name: str) -> str:
        """
        Zkopiruje soubor do cilove slozky.
        destination: 'sent' | 'redo' | 'redo_error' | 'skipped'
        Vraci 'OK' nebo chybovou zpravu.
        """
        result = await self.call_tool("sharepoint_copy_file", {
            "item_id": item_id,
            "destination": destination,
            "file_name": file_name,
        })
        logger.debug(f"  [SharePointAgent] copy_file({file_name} -> {destination}): {result}")
        return result
