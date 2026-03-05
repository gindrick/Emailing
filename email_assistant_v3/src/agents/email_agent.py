"""
EmailAgent - specializovany agent pro zpracovani emailu a PDF.

Zodpovednost:
- Nacteni mapovani zakaznik->email z Excelu
- Nacteni skip prefixu z Excelu
- Extrakce textu z PDF (base64 vstup)
- LLM extrakce Bill To ID + osloveni z PDF textu
- Odeslani emailu s PDF prilohou (SMTP)
- Odeslani souhrnneho emailu bez prilohy (SMTP)

Povolene nastroje (5): excel_load_customer_mapping, excel_load_skip_prefixes,
                        pdf_extract_text, smtp_send_email, smtp_send_plain_email

LLM se pouziva primo (ne pres MCP) pro:
- Strukturovanou extrakci Bill To + osloveni z PDF textu
- Formatovani souhrnneho emailu v cestine
"""

from __future__ import annotations

import json
import logging
import re

from src.agents.base_agent import BaseAgent
from src.models import DocumentExtraction

logger = logging.getLogger(__name__)


class EmailAgent(BaseAgent):
    """Agent pro Excel data, PDF extrakci a odesilani emailu."""

    TOOL_WHITELIST = [
        "excel_load_customer_mapping",
        "excel_load_skip_prefixes",
        "pdf_extract_text",
        "smtp_send_email",
        "smtp_send_plain_email",
    ]

    async def load_customer_mapping(self) -> dict[str, str]:
        """
        Nacte mapovani customer_id -> emaily z Excel souboru.
        Vraci dict {customer_id: 'email1, email2'}.
        """
        result = await self.call_tool("excel_load_customer_mapping")
        mapping = json.loads(result)
        logger.info(f"  [EmailAgent] Zakazniku nacteno: {len(mapping)}")
        return mapping

    async def load_skip_prefixes(self) -> tuple[str, ...]:
        """
        Nacte seznam Bill-To prefixu pro preskoceni z inputs/skip.xlsx.
        Vraci tuple retezcu.
        """
        result = await self.call_tool("excel_load_skip_prefixes")
        prefixes = tuple(json.loads(result))
        logger.info(f"  [EmailAgent] Skip prefixu nacteno: {len(prefixes)}")
        return prefixes

    async def extract_pdf_text(self, pdf_b64: str) -> str:
        """
        Extrahuje plain text z PDF (base64 vstup).
        Vraci textovy obsah dokumentu.
        """
        return await self.call_tool("pdf_extract_text", {"pdf_b64": pdf_b64})

    async def llm_extract(
        self, pdf_text: str, file_name: str, customer_id_from_filename: str
    ) -> DocumentExtraction:
        """
        Pouziva LLM pro strukturovanou extrakci z PDF textu:
        1. Bill To customer ID (overeni spravnosti souboru)
        2. Personalni ceske osloveni (jmeno/firma)

        Fallback: regex pro Bill To + obecne 'Dobry den,' pri selhani LLM.
        """
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
            extraction = await self._llm.call_structured(
                messages=messages,
                response_model=DocumentExtraction,
                temperature=0.0,
            )
            return extraction
        except Exception as e:
            logger.warning(f"  [EmailAgent] LLM extrakce selhala ({e}), pouzivam regex fallback")
            match = re.search(r"Bill\s*[- ]?To\s*[:#]?\s*([A-Za-z0-9]+)", pdf_text, flags=re.IGNORECASE)
            bill_to = match.group(1).strip() if match else None
            return DocumentExtraction(
                bill_to_customer_id=bill_to,
                salutation="Dobry den,",
                is_person=False,
            )

    async def send_email(
        self,
        to_recipients: str,
        subject: str,
        body: str,
        pdf_b64: str,
        file_name: str,
        bcc_recipients: str = "",
    ) -> str:
        """
        Odesle email s PDF prilohou.
        to_recipients, bcc_recipients: emaily oddelene carkou.
        Vraci 'OK' nebo chybovou zpravu.
        """
        result = await self.call_tool("smtp_send_email", {
            "to_recipients": to_recipients,
            "subject": subject,
            "body": body,
            "pdf_b64": pdf_b64,
            "file_name": file_name,
            "bcc_recipients": bcc_recipients,
        })
        logger.debug(f"  [EmailAgent] smtp_send_email -> {result}")
        return result

    async def send_summary_email(
        self, recipient: str, summary: dict
    ) -> str:
        """
        Zformuluje a odesle souhrnny report email po zpracovani.
        LLM vytvori ctitelny text ze surovych statistik.
        Vraci 'OK' nebo chybovou zpravu.
        """
        email_body = await self._llm_format_summary(summary)
        subject = (
            f"Email Assistant v3 - report zpracovani "
            f"({summary['completed']} uspesne / {summary['redo'] + summary['failed']} chyb)"
        )
        result = await self.call_tool("smtp_send_plain_email", {
            "to_recipients": recipient,
            "subject": subject,
            "body": email_body,
        })
        logger.info(f"  [EmailAgent] Souhrnny email -> {recipient}: {result}")
        return result

    async def _llm_format_summary(self, summary: dict) -> str:
        """
        LLM preformatuje technicka data do ctitelneho emailu v cestine.
        Fallback na plain text pri selhani LLM.
        """
        error_items_text = ""
        if summary.get("error_items"):
            lines = [
                f"  - {i['file_name']} [{i['status']}]: {i['error']}"
                for i in summary["error_items"]
            ]
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
            response = await self._llm.call(messages=messages, temperature=0.3)
            return response.choices[0].message.content or self._plain_summary(summary)
        except Exception as e:
            logger.warning(f"  [EmailAgent] LLM summary selhalo ({e}), pouzivam plain-text fallback")
            return self._plain_summary(summary)

    def _plain_summary(self, summary: dict) -> str:
        """Jednoduchy plain-text fallback pro souhrnny email."""
        lines = [
            "Email Assistant v3 - Zprava o behu",
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
