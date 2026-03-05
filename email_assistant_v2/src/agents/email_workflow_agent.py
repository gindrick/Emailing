"""
EmailWorkflowAgent - Workflow Agent pro zpracovani emailu s PDF prilohou.

Architektura:
- Workflow Agent pattern s pevne definovanymi kroky (uzly)
- MCP tools pro vsechny I/O operace (SharePoint, Excel, DB, SMTP)
- LLM (pres LiteLLM proxy) pro:
  * Extrakci Bill To customer ID z PDF textu (misto fragileho regexu)
  * Generovani personalniho ceskeho osloveni (jmeno/prijmeni z PDF)

Kroky workflow:
  1. initialize   - SharePoint a DB inicializace (MCP tools)
  2. load_data    - Nacteni dat z Excelu a SharePointu (MCP tools)
  3. process_docs - Zpracovani dokumentu s LLM extrakcí per dokument
  4. export       - Export reportu (MCP tool)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from src.clients.llm_client import LLMClient
from src.clients.mcp_client import MCPClient
from src.models import DocumentExtraction
from src.settings import AgentSettings
from src.utils import (
    canonical_customer_id,
    extract_customer_id_from_filename_start,
    match_skip_prefix,
    normalize_customer_id,
    parse_recipient_list,
)

logger = logging.getLogger(__name__)


class EmailWorkflowAgent:
    """
    Workflow Agent pro automatizovane odesilani PDF dokumentu zakaznikum.

    LLM se pouziva v kroku 'process_docs' pro kazdy dokument:
    - Extrakce Bill To customer ID z textu PDF
    - Generovani personalniho ceskeho osloveni
    """

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.llm = LLMClient(model=settings.litellm_model)
        self.mcp = MCPClient(server_url=settings.mcp_server_url)

        # Stav workflow - plnen v prubehu kroku
        self._sp_info: dict = {}          # drive_id, folder IDs, source path
        self._customer_map: dict = {}     # customer_id -> "email1, email2"
        self._skip_prefixes: tuple = ()   # prefixes z skip.xlsx
        self._pdf_items: list[dict] = []  # [{id, name}]
        self._batch_ids: list[str] = []   # item_id k zpracovani

        # Statistiky
        self.stats = {"sent": 0, "skipped": 0, "errors": 0}

    # ============================================================
    # Hlavni vstupni bod
    # ============================================================

    async def run(self) -> dict:
        """
        Spusti cely workflow. Vraci statistiky zpracovani.
        """
        logger.info("=" * 65)
        logger.info("  Email Assistant v2 - Workflow Agent")
        logger.info("=" * 65)

        await self.mcp.connect()
        try:
            await self._step_initialize()
            await self._step_load_data()
            await self._step_process_documents()
            await self._step_export_reports()
            await self._step_send_summary()
        finally:
            await self.mcp.disconnect()

        logger.info("=" * 65)
        logger.info(f"  HOTOVO | Odeslano: {self.stats['sent']} | Preskoceno: {self.stats['skipped']} | Chyby: {self.stats['errors']}")
        logger.info("=" * 65)
        return self.stats

    # ============================================================
    # Krok 1: Inicializace
    # ============================================================

    async def _step_initialize(self) -> None:
        """
        Inicializuje SharePoint (drive, slozky) a SQLite databazi.
        Pouziva MCP tools: sharepoint_initialize, db_initialize.
        """
        logger.info("[1/4] Inicializace SharePoint a databaze...")

        sp_result = await self.mcp.call_tool("sharepoint_initialize", {})
        self._sp_info = json.loads(sp_result)
        logger.info(f"  Drive: {self._sp_info.get('drive_id', '?')}")
        logger.info(f"  Zdrojova slozka: {self._sp_info.get('source_folder_path', '?')}")
        logger.info(f"  Sent: {self._sp_info.get('sent_folder_id', '?')}")

        await self.mcp.call_tool("db_initialize", {})
        logger.info("  SQLite databaze inicializovana.")

    # ============================================================
    # Krok 2: Nacteni dat
    # ============================================================

    async def _step_load_data(self) -> None:
        """
        Nacte mapping zakaznik->email z Excelu, skip prefixes,
        seznam PDF ze SharePointu, zaseje DB a vrati davku k zpracovani.
        Pouziva MCP tools: excel_*, sharepoint_list_pdfs, db_seed_items, db_get_batch.
        """
        logger.info("[2/4] Nacteni dat...")

        # Zakaznicka mapa
        map_result = await self.mcp.call_tool("excel_load_customer_mapping", {})
        self._customer_map = json.loads(map_result)
        logger.info(f"  Zakazniku nacteno: {len(self._customer_map)}")

        # Skip prefixes
        skip_result = await self.mcp.call_tool("excel_load_skip_prefixes", {})
        self._skip_prefixes = tuple(json.loads(skip_result))
        logger.info(f"  Skip prefixu: {len(self._skip_prefixes)}")

        # PDF ze SharePointu
        pdf_result = await self.mcp.call_tool("sharepoint_list_pdfs", {})
        self._pdf_items = json.loads(pdf_result)
        logger.info(f"  PDF souboru nalezeno: {len(self._pdf_items)}")

        if not self._pdf_items:
            logger.info("  Zadne PDF soubory ke zpracovani.")
            return

        # Zaseti DB
        items_json = json.dumps(self._pdf_items)
        seeded = await self.mcp.call_tool("db_seed_items", {"items_json": items_json})
        logger.info(f"  DB zaznamu vlozeno/aktualizovano: {seeded}")

        # Davka k zpracovani
        item_ids_json = json.dumps([i["id"] for i in self._pdf_items])
        batch_result = await self.mcp.call_tool("db_get_batch", {"item_ids_json": item_ids_json})
        self._batch_ids = json.loads(batch_result)
        logger.info(f"  Davka k zpracovani: {len(self._batch_ids)} / {len(self._pdf_items)} (BATCH_SIZE={self.settings.batch_size})")

    # ============================================================
    # Krok 3: Zpracovani dokumentu
    # ============================================================

    async def _step_process_documents(self) -> None:
        """
        Iteruje pres davku dokumentu. Pro kazdy dokument:
        - Python logika: skip check, ID z nazvu, lookup emailu
        - MCP tools: stazeni PDF, odeslani emailu, presun, DB update
        - LLM: extrakce Bill To ID z PDF textu, generovani osloveni
        """
        logger.info(f"[3/4] Zpracovani {len(self._batch_ids)} dokumentu...")

        if not self._batch_ids:
            logger.info("  Prazdna davka, preskakuji.")
            return

        pdf_by_id = {item["id"]: item for item in self._pdf_items}

        for idx, item_id in enumerate(self._batch_ids, 1):
            item = pdf_by_id.get(item_id)
            if not item:
                logger.warning(f"  [{idx}] item_id={item_id} nenalezen v pdf_items, preskakuji.")
                continue

            file_name = item["name"]
            stem = Path(file_name).stem
            logger.info(f"\n  [{idx}/{len(self._batch_ids)}] {file_name}")

            try:
                await self._process_single(item_id, file_name, stem)
            except Exception as e:
                logger.error(f"  [ERROR] Neocekavana chyba u {file_name}: {e}")
                await self._move_to_redo(item_id, file_name, str(e), error_bucket=True)
                self.stats["errors"] += 1

    async def _process_single(self, item_id: str, file_name: str, stem: str) -> None:
        """Zpracuje jeden PDF dokument - kompletni pipeline."""

        # --- 1. Skip check (Bill-To prefix) ---
        matched_prefix = match_skip_prefix(stem, self._skip_prefixes)
        if matched_prefix:
            await self.mcp.call_tool("sharepoint_copy_file", {
                "item_id": item_id, "destination": "skipped", "file_name": file_name,
            })
            await self.mcp.call_tool("db_mark_skipped", {"item_id": item_id})
            logger.info(f"    [SKIP] Bill-To prefix '{matched_prefix}' -> skipped")
            self.stats["skipped"] += 1
            return

        # --- 2. Customer ID z nazvu souboru (Python regex) ---
        customer_id = extract_customer_id_from_filename_start(stem)
        if not customer_id:
            await self._move_to_redo(item_id, file_name, "Nelze extrahovat customer ID z nazvu souboru")
            self.stats["skipped"] += 1
            return

        # --- 3. Lookup emailu ---
        canonical_id = canonical_customer_id(customer_id)
        customer_email = self._customer_map.get(canonical_id)
        if not customer_email:
            await self._move_to_redo(item_id, file_name, f"Neni email pro customer ID '{customer_id}'")
            self.stats["skipped"] += 1
            return

        # --- 4. Aktualizace DB metadat ---
        recipient_raw = self.settings.test_recipient_email if self.settings.test_mode else customer_email
        await self.mcp.call_tool("db_ensure_file", {
            "item_id": item_id,
            "file_name": file_name,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "target_recipient": recipient_raw,
        })

        # --- 5. Kontrola jestli uz zpracovano ---
        state_json = await self.mcp.call_tool("db_get_file_state", {"item_id": item_id})
        state = json.loads(state_json) or {}
        if state.get("moved_to_sent") == 1:
            logger.info("    [SKIP] Jiz dokonceno (moved_to_sent=1)")
            self.stats["skipped"] += 1
            return

        # --- 6. Stazeni PDF ---
        await self.mcp.call_tool("db_mark_status", {"item_id": item_id, "status": "sending"})
        logger.info("    Stahuji PDF ze SharePointu...")
        pdf_b64 = await self.mcp.call_tool("sharepoint_download_pdf", {"item_id": item_id})

        # --- 7. LLM extrakce (Bill To + osloveni) ---
        logger.info("    LLM: Extrakce informaci z PDF...")
        pdf_text = await self.mcp.call_tool("pdf_extract_text", {"pdf_b64": pdf_b64})
        extraction = await self._llm_extract(pdf_text, file_name, customer_id)
        logger.info(f"    LLM: bill_to='{extraction.bill_to_customer_id}' | salutation='{extraction.salutation}'")

        # --- 8. Validace Bill To ID ---
        if not extraction.bill_to_customer_id:
            await self._move_to_redo(item_id, file_name, "LLM nenaslo Bill To ID v PDF", error_bucket=True)
            self.stats["errors"] += 1
            return

        if normalize_customer_id(customer_id) != normalize_customer_id(extraction.bill_to_customer_id):
            reason = f"Neshoda ID: nazev='{customer_id}' vs Bill-To='{extraction.bill_to_customer_id}'"
            await self._move_to_redo(item_id, file_name, reason, error_bucket=True)
            self.stats["errors"] += 1
            return

        # --- 9. Sestaveni emailu ---
        subject = self.settings.email_subject_template.format(
            customer_id=customer_id, file_name=file_name
        )
        body_base = self.settings.email_body_template.format(
            customer_id=customer_id, file_name=file_name, customer_email=customer_email
        )
        body = f"{extraction.salutation}\n\n{body_base}"

        recipient_list = parse_recipient_list(
            self.settings.test_recipient_email if self.settings.test_mode else customer_email
        )
        bcc_list = [] if self.settings.test_mode else parse_recipient_list(self.settings.production_bcc)

        if self.settings.test_mode:
            body += f"\n\n[TEST MODE] Skutecny zakaznik: {customer_email}"

        to_recipients = ", ".join(recipient_list)
        bcc_recipients = ", ".join(bcc_list)

        # --- 10. Odeslani emailu ---
        logger.info(f"    Odesilam email na: {to_recipients}")
        send_result = await self.mcp.call_tool("smtp_send_email", {
            "to_recipients": to_recipients,
            "subject": subject,
            "body": body,
            "pdf_b64": pdf_b64,
            "file_name": file_name,
            "bcc_recipients": bcc_recipients,
        })
        if send_result != "OK":
            await self._move_to_redo(item_id, file_name, f"Chyba odeslani: {send_result}", error_bucket=True)
            self.stats["errors"] += 1
            return

        await self.mcp.call_tool("db_mark_email_sent", {"item_id": item_id})
        logger.info(f"    [OK] Email odeslan -> {to_recipients}")

        # --- 11. Presun do sent ---
        await self.mcp.call_tool("db_mark_status", {"item_id": item_id, "status": "moving"})
        copy_result = await self.mcp.call_tool("sharepoint_copy_file", {
            "item_id": item_id, "destination": "sent", "file_name": file_name,
        })
        if copy_result != "OK":
            logger.warning(f"    [WARN] Nelze zkopirovat do sent: {copy_result}")
        await self.mcp.call_tool("db_mark_moved", {"item_id": item_id})
        logger.info("    [OK] Zkopirovan do sent")

        self.stats["sent"] += 1

    # ============================================================
    # LLM extrakce z PDF
    # ============================================================

    async def _llm_extract(
        self, pdf_text: str, file_name: str, customer_id_from_filename: str
    ) -> DocumentExtraction:
        """
        Pouziva LLM pro extrakci:
        1. Bill To customer ID z textu PDF (nahrazuje krehky regex)
        2. Personalni ceske osloveni (jmeno/prijmeni pokud nalezeno)

        Fallback na regex a obecne osloveni pri selhani LLM.
        """
        # Omezeni delky textu aby se veslo do kontextoveho okna
        max_chars = 8_000
        text_excerpt = pdf_text[:max_chars] if len(pdf_text) > max_chars else pdf_text

        messages = [
            {
                "role": "system",
                "content": (
                    "Jsi analyza dokumentu. Extrahujes specificke informace z textu PDF faktur/dokumentu.\n\n"
                    "BILL TO CUSTOMER ID:\n"
                    "Hledej text jako 'Bill To:', 'Bill-To:', 'Billto:', 'Zakaznik:', 'Customer:' nasledovany "
                    "alfanumerickem ID zakaznika. Vrat None pokud neni nalezeno.\n\n"
                    "OSLOVENI (cesky):\n"
                    "Pokud najdes krestni jmeno a prijmeni fyzicke osoby:\n"
                    "- Muz (prijmeni bez -ova/-a koncu): 'Vazeny pane [Prijmeni],'\n"
                    "- Zena (prijmeni na -ova/-a): 'Vazena pani [Prijmeni],'\n"
                    "Pokud je to firma nebo nejde urcit pohlavni: 'Dobry den,'"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Soubor: {file_name}\n"
                    f"Zname customer ID z nazvu souboru: {customer_id_from_filename}\n\n"
                    f"Text PDF:\n{text_excerpt}\n\n"
                    "Extrahuj Bill To customer ID a osloveni."
                ),
            },
        ]

        try:
            extraction = await self.llm.call_structured(
                messages=messages,
                response_model=DocumentExtraction,
                temperature=0.0,
            )
            return extraction
        except Exception as e:
            logger.warning(f"    LLM extrakce selhala ({e}), pouzivam regex fallback")
            # Fallback: regex pro Bill To, obecne osloveni
            match = re.search(r"Bill\s*[- ]?To\s*[:#]?\s*([A-Za-z0-9]+)", pdf_text, flags=re.IGNORECASE)
            bill_to = match.group(1).strip() if match else None
            return DocumentExtraction(
                bill_to_customer_id=bill_to,
                salutation="Dobry den,",
                is_person=False,
            )

    # ============================================================
    # Krok 4: Export reportu
    # ============================================================

    async def _step_export_reports(self) -> None:
        """Exportuje reporty ze SQLite do Excel souboru."""
        logger.info("[4/5] Export reportu...")
        result = await self.mcp.call_tool("db_export_reports", {})
        logger.info(f"  {result}")

    # ============================================================
    # Krok 5: Souhrnny informacni email
    # ============================================================

    async def _step_send_summary(self) -> None:
        """
        Nacte statistiky z DB, LLM je zformuluje do srozumitelneho textu
        a odesle souhrnny email na SUMMARY_RECIPIENT_EMAIL.
        Pokud SUMMARY_RECIPIENT_EMAIL neni nastaven, krok se preskoci.
        """
        recipient = self.settings.summary_recipient_email
        if not recipient:
            logger.info("[5/5] SUMMARY_RECIPIENT_EMAIL neni nastaven, souhrnny email se neodesila.")
            return

        logger.info(f"[5/5] Souhrnny email -> {recipient}...")

        # Nacteni statistik z DB
        summary_json = await self.mcp.call_tool("db_get_summary", {})
        summary = json.loads(summary_json)

        # LLM zformuluje text emailu ze surových statistik
        email_body = await self._llm_format_summary(summary)

        subject = f"Email Assistant - report zpracovani ({summary['completed']} uspesne / {summary['redo'] + summary['failed']} chyb)"

        send_result = await self.mcp.call_tool("smtp_send_plain_email", {
            "to_recipients": recipient,
            "subject": subject,
            "body": email_body,
        })

        if send_result == "OK":
            logger.info(f"  [OK] Souhrnny email odeslan na {recipient}")
        else:
            logger.warning(f"  [WARN] Souhrnny email se nepodaril: {send_result}")

    async def _llm_format_summary(self, summary: dict) -> str:
        """
        LLM preformatuje technicka data ze SQLite do ctitelneho
        emailu v cestine s prehlednou strukturou.
        Fallback na plain-text formatovani pri selhani LLM.
        """
        error_items_text = ""
        if summary.get("error_items"):
            lines = [f"  - {i['file_name']} [{i['status']}]: {i['error']}" for i in summary["error_items"]]
            error_items_text = "\n".join(lines)

        messages = [
            {
                "role": "system",
                "content": (
                    "Jsi asistent ktery pise souhrnne reporty o zpracovani dokumentu. "
                    "Pis cesky, strucne a prehledne. Pouzij jednoduche formatovani (bez HTML, bez markdown). "
                    "Email musi obsahovat: celkovy pocet, uspesne odeslane, preskocene, k provereni/v chybe, "
                    "a pokud jsou chyby - seznam chybovych souboru s duvodem."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Zformuluj souhrnny email o behu email-assistant na zaklade techto dat:\n\n"
                    f"Celkem dokumentu v DB: {summary['total']}\n"
                    f"Uspesne dokonceno (email odeslan + presunut): {summary['completed']}\n"
                    f"Email odeslan, ceka na presun: {summary['email_sent_pending_move']}\n"
                    f"Preskoceno (skip.xlsx): {summary['skipped']}\n"
                    f"K provereni (redo slozka): {summary['redo']}\n"
                    f"Chyba zpracovani: {summary['failed']}\n"
                    f"Ceka na zpracovani: {summary['pending']}\n"
                    + (f"\nSoubory s chybou/redo:\n{error_items_text}" if error_items_text else "")
                ),
            },
        ]

        try:
            response = await self.llm.call(messages=messages, temperature=0.3)
            return response.choices[0].message.content or self._plain_summary(summary)
        except Exception as e:
            logger.warning(f"  LLM summary selhalo ({e}), pouzivam plain-text fallback")
            return self._plain_summary(summary)

    def _plain_summary(self, summary: dict) -> str:
        """Jednoduchy plain-text fallback pro souhrnny email."""
        lines = [
            "Email Assistant v2 - Zprava o behu",
            "=" * 40,
            f"Celkem dokumentu:        {summary['total']}",
            f"Uspesne odeslano:        {summary['completed']}",
            f"Preskoceno (skip.xlsx):  {summary['skipped']}",
            f"K provereni (redo):      {summary['redo']}",
            f"Chyba zpracovani:        {summary['failed']}",
            f"Ceka na zpracovani:      {summary['pending']}",
        ]
        if summary.get("error_items"):
            lines.append("\nSoubory vyzadujici pozornost:")
            for item in summary["error_items"]:
                lines.append(f"  - {item['file_name']} [{item['status']}]: {item['error']}")
        return "\n".join(lines)

    # ============================================================
    # Pomocne metody
    # ============================================================

    async def _move_to_redo(
        self, item_id: str, file_name: str, reason: str, error_bucket: bool = False
    ) -> None:
        """Presune soubor do redo nebo redo/error slozky a aktualizuje DB."""
        destination = "redo_error" if error_bucket else "redo"
        await self.mcp.call_tool("db_mark_status", {
            "item_id": item_id, "status": "failed", "error_message": reason,
        })
        try:
            await self.mcp.call_tool("sharepoint_copy_file", {
                "item_id": item_id, "destination": destination, "file_name": file_name,
            })
            await self.mcp.call_tool("db_mark_redo", {
                "item_id": item_id, "error_message": reason,
            })
            logger.info(f"    [REDO] -> {destination}: {file_name}")
        except Exception as e:
            logger.error(f"    [ERROR] Nelze zkopirovat do {destination}: {e}")
        logger.warning(f"    [WARN] {file_name}: {reason}")
