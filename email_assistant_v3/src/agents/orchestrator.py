"""
PlanExecuteOrchestrator - koordinuje tri specializovane sub-agenty.

Architektura (Multi-Agent Swarm):
  SharePointAgent  (4 nastroje)  - SharePoint operace
  DatabaseAgent    (12 nastroju) - SQLite state tracking
  EmailAgent       (5 nastroju)  - Excel, PDF extrakce, SMTP

Orchestrator riadi Plan-Execute workflow:
  1. initialize       - SP inicializace + DB inicializace
  2. load_data        - Nacteni dat, seedovani DB, priprava davky
  3. process_documents- Zpracovani kazdeho PDF (skip/send/redo)
  4. export_reports   - Export reportu do Excel
  5. send_summary     - Souhrnny email po dokonceni

Kazdy krok se pokusi 2x (retry) pri selhani.
LLM se pouziva POUZE v EmailAgent pro extrakci z PDF a formatovani reportu.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.agents.database_agent import DatabaseAgent
from src.agents.email_agent import EmailAgent
from src.agents.sharepoint_agent import SharePointAgent
from src.clients.llm_client import LLMClient
from src.clients.mcp_client import MCPClient
from src.settings import AgentSettings
from src.utils import (
    canonical_customer_id,
    extract_customer_id_from_filename_start,
    match_skip_prefix,
    normalize_customer_id,
    parse_recipient_list,
)

logger = logging.getLogger(__name__)

# Definice planu: (krok_id, popis)
PLAN: list[tuple[str, str]] = [
    ("initialize", "Inicializace SharePoint a databaze"),
    ("load_data", "Nacteni dat a priprava davky"),
    ("process_documents", "Zpracovani dokumentu"),
    ("export_reports", "Export reportu"),
    ("send_summary", "Odeslani souhrnneho emailu"),
]

MAX_RETRIES = 2


class PlanExecuteOrchestrator:
    """
    Orchestrator koordinujici tri specializovane sub-agenty.

    Pouziva Plan-Execute vzor:
    - Pevne definovany plan (5 kroku)
    - Kazdy krok delegovan na prislusneho sub-agenta
    - Retry mechanismus pri selhani kroku (max 2 pokusy)

    Sdileny stav workflow je udrzovan v orchestratoru (ne v agentech),
    aby agenti zustali bezstavovi a snadno testovatelni.
    """

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

        # Sdilene klienty
        mcp = MCPClient(server_url=settings.mcp_server_url)
        llm = LLMClient(model=settings.litellm_model)

        # Specializovani sub-agenti (sdileji stejne klienty)
        self.sp = SharePointAgent(mcp, llm)
        self.db = DatabaseAgent(mcp, llm)
        self.email = EmailAgent(mcp, llm)

        # Ulozime mcp pro connect/disconnect
        self._mcp = mcp

        # Sdileny stav workflow
        self._sp_info: dict = {}
        self._customer_map: dict[str, str] = {}
        self._skip_prefixes: tuple[str, ...] = ()
        self._pdf_items: list[dict] = []
        self._batch_ids: list[str] = []

        # Statistiky
        self.stats = {"sent": 0, "skipped": 0, "errors": 0}

    # ============================================================
    # Hlavni vstupni bod
    # ============================================================

    async def run(self) -> dict:
        """Spusti Plan-Execute workflow. Vraci statistiky zpracovani."""
        logger.info("=" * 65)
        logger.info("  Email Assistant v3 - Multi-Agent Plan-Execute")
        logger.info("  Agenti: SharePointAgent | DatabaseAgent | EmailAgent")
        logger.info("=" * 65)

        await self._mcp.connect()
        try:
            for step_id, step_desc in PLAN:
                await self._execute_step(step_id, step_desc)
        finally:
            await self._mcp.disconnect()

        logger.info("=" * 65)
        logger.info(
            f"  HOTOVO | Odeslano: {self.stats['sent']} | "
            f"Preskoceno: {self.stats['skipped']} | "
            f"Chyby: {self.stats['errors']}"
        )
        logger.info("=" * 65)
        return self.stats

    async def _execute_step(self, step_id: str, step_desc: str) -> None:
        """
        Provede jeden krok planu s retry mechanismem.
        Pri opakovanem selhani zaloguje chybu a pokracuje na dalsi krok.
        """
        method = getattr(self, f"_step_{step_id}")
        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"\n[PLAN] Krok: {step_desc}" + (f" (pokus {attempt}/{MAX_RETRIES})" if attempt > 1 else ""))
                await method()
                return  # Uspech
            except Exception as e:
                last_error = e
                logger.warning(f"  [RETRY] Krok '{step_id}' selhal (pokus {attempt}): {e}")

        # Vsechny pokusy selhaly
        logger.error(f"  [FAIL] Krok '{step_id}' selhal po {MAX_RETRIES} pokusech: {last_error}")
        # Nekritické kroky (export, summary) neukoncuji beh
        if step_id in ("export_reports", "send_summary"):
            logger.warning(f"  Pokracuji bez kroku '{step_id}'.")
        else:
            raise RuntimeError(f"Kriticky krok '{step_id}' selhal: {last_error}") from last_error

    # ============================================================
    # Krok 1: Inicializace
    # ============================================================

    async def _step_initialize(self) -> None:
        """
        SharePointAgent: inicializace drive a slozkove struktury.
        DatabaseAgent:   inicializace SQLite databaze.
        """
        # SharePointAgent
        self._sp_info = await self.sp.initialize()

        # DatabaseAgent
        await self.db.initialize()
        logger.info("  SQLite databaze inicializovana.")

    # ============================================================
    # Krok 2: Nacteni dat
    # ============================================================

    async def _step_load_data(self) -> None:
        """
        EmailAgent:      nacteni customer mapy + skip prefixu z Excelu.
        SharePointAgent: vylistovani PDF souboru.
        DatabaseAgent:   seedovani DB + nacteni davky k zpracovani.
        """
        # EmailAgent: Excel data
        self._customer_map = await self.email.load_customer_mapping()
        self._skip_prefixes = await self.email.load_skip_prefixes()

        # SharePointAgent: seznam PDF
        self._pdf_items = await self.sp.list_pdfs()

        if not self._pdf_items:
            logger.info("  Zadne PDF soubory ke zpracovani.")
            return

        # DatabaseAgent: seed + batch
        await self.db.seed_items(self._pdf_items)
        item_ids = [i["id"] for i in self._pdf_items]
        self._batch_ids = await self.db.get_batch(item_ids)
        logger.info(
            f"  Davka: {len(self._batch_ids)} / {len(self._pdf_items)} "
            f"(BATCH_SIZE={self.settings.batch_size})"
        )

    # ============================================================
    # Krok 3: Zpracovani dokumentu
    # ============================================================

    async def _step_process_documents(self) -> None:
        """Iteruje pres davku a zpracuje kazdy dokument."""
        if not self._batch_ids:
            logger.info("  Prazdna davka, preskakuji.")
            return

        logger.info(f"  Zpracovani {len(self._batch_ids)} dokumentu...")
        pdf_by_id = {item["id"]: item for item in self._pdf_items}

        for idx, item_id in enumerate(self._batch_ids, 1):
            item = pdf_by_id.get(item_id)
            if not item:
                logger.warning(f"  [{idx}] item_id={item_id} nenalezen, preskakuji.")
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
        """
        Kompletni pipeline pro jeden PDF dokument.

        Sekvence:
        skip check -> customer ID -> email lookup -> DB metadata ->
        stavova kontrola -> stazeni PDF -> LLM extrakce -> validace ->
        sestaveni emailu -> odeslani -> presun do sent
        """

        # --- 1. Skip check (Bill-To prefix ze skip.xlsx) ---
        matched_prefix = match_skip_prefix(stem, self._skip_prefixes)
        if matched_prefix:
            await self.sp.copy_file(item_id, "skipped", file_name)
            await self.db.mark_skipped(item_id)
            logger.info(f"    [SKIP] Bill-To prefix '{matched_prefix}' -> skipped")
            self.stats["skipped"] += 1
            return

        # --- 2. Customer ID z nazvu souboru ---
        customer_id = extract_customer_id_from_filename_start(stem)
        if not customer_id:
            await self._move_to_redo(item_id, file_name, "Nelze extrahovat customer ID z nazvu souboru")
            self.stats["skipped"] += 1
            return

        # --- 3. Lookup emailu z customer mapy ---
        canonical_id = canonical_customer_id(customer_id)
        customer_email = self._customer_map.get(canonical_id)
        if not customer_email:
            await self._move_to_redo(item_id, file_name, f"Neni email pro customer ID '{customer_id}'")
            self.stats["skipped"] += 1
            return

        # --- 4. Ulozeni metadat do DB ---
        recipient_raw = self.settings.test_recipient_email if self.settings.test_mode else customer_email
        await self.db.ensure_file(item_id, file_name, customer_id, customer_email, recipient_raw)

        # --- 5. Kontrola jestli uz zpracovano ---
        state = await self.db.get_file_state(item_id)
        if state.get("moved_to_sent") == 1:
            logger.info("    [SKIP] Jiz dokonceno (moved_to_sent=1)")
            self.stats["skipped"] += 1
            return

        # --- 6. Stazeni PDF (SharePointAgent) ---
        await self.db.mark_status(item_id, "sending")
        logger.info("    SharePointAgent: stahuji PDF...")
        pdf_b64 = await self.sp.download_pdf(item_id)

        # --- 7. Extrakce textu + LLM analyza (EmailAgent) ---
        logger.info("    EmailAgent: extrakce textu z PDF...")
        pdf_text = await self.email.extract_pdf_text(pdf_b64)

        logger.info("    EmailAgent: LLM extrakce Bill To + osloveni...")
        extraction = await self.email.llm_extract(pdf_text, file_name, customer_id)
        logger.info(
            f"    LLM: bill_to='{extraction.bill_to_customer_id}' | "
            f"salutation='{extraction.salutation}'"
        )

        # --- 8. Validace Bill To ID ---
        if not extraction.bill_to_customer_id:
            await self._move_to_redo(item_id, file_name, "LLM nenaslo Bill To ID v PDF", error_bucket=True)
            self.stats["errors"] += 1
            return

        if normalize_customer_id(customer_id) != normalize_customer_id(extraction.bill_to_customer_id):
            reason = (
                f"Neshoda ID: nazev='{customer_id}' vs Bill-To='{extraction.bill_to_customer_id}'"
            )
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

        # --- 10. Odeslani emailu (EmailAgent) ---
        logger.info(f"    EmailAgent: odesilam email na {to_recipients}...")
        send_result = await self.email.send_email(
            to_recipients=to_recipients,
            subject=subject,
            body=body,
            pdf_b64=pdf_b64,
            file_name=file_name,
            bcc_recipients=bcc_recipients,
        )
        if send_result != "OK":
            await self._move_to_redo(item_id, file_name, f"Chyba odeslani: {send_result}", error_bucket=True)
            self.stats["errors"] += 1
            return

        await self.db.mark_email_sent(item_id)
        logger.info(f"    [OK] Email odeslan -> {to_recipients}")

        # --- 11. Presun do sent (SharePointAgent + DatabaseAgent) ---
        await self.db.mark_status(item_id, "moving")
        copy_result = await self.sp.copy_file(item_id, "sent", file_name)
        if copy_result != "OK":
            logger.warning(f"    [WARN] Nelze zkopirovat do sent: {copy_result}")
        await self.db.mark_moved(item_id)
        logger.info("    [OK] Zkopirovan do sent")

        self.stats["sent"] += 1

    # ============================================================
    # Krok 4: Export reportu
    # ============================================================

    async def _step_export_reports(self) -> None:
        """DatabaseAgent: exportuje reporty do Excel souboru v output/."""
        result = await self.db.export_reports()
        logger.info(f"  Export reportu: {result}")

    # ============================================================
    # Krok 5: Souhrnny email
    # ============================================================

    async def _step_send_summary(self) -> None:
        """
        DatabaseAgent: nacte statistiky z DB.
        EmailAgent:    LLM zformuluje + odesle souhrnny email.
        Preskoci pokud SUMMARY_RECIPIENT_EMAIL neni nastaven.
        """
        recipient = self.settings.summary_recipient_email
        if not recipient:
            logger.info("  SUMMARY_RECIPIENT_EMAIL neni nastaven, souhrnny email se neodesila.")
            return

        logger.info(f"  Souhrnny email -> {recipient}...")
        summary = await self.db.get_summary()
        await self.email.send_summary_email(recipient, summary)

    # ============================================================
    # Pomocna metoda: presun do redo
    # ============================================================

    async def _move_to_redo(
        self, item_id: str, file_name: str, reason: str, error_bucket: bool = False
    ) -> None:
        """
        Presune soubor do redo nebo redo_error slozky a aktualizuje DB.
        SharePointAgent + DatabaseAgent spolupracuji.
        """
        destination = "redo_error" if error_bucket else "redo"
        await self.db.mark_status(item_id, "failed", reason)
        try:
            await self.sp.copy_file(item_id, destination, file_name)
            await self.db.mark_redo(item_id, reason)
            logger.info(f"    [REDO] -> {destination}: {file_name}")
        except Exception as e:
            logger.error(f"    [ERROR] Nelze zkopirovat do {destination}: {e}")
        logger.warning(f"    [WARN] {file_name}: {reason}")
