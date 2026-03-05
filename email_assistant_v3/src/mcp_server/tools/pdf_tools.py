from __future__ import annotations

import base64
import io


def pdf_extract_text(pdf_b64: str) -> str:
    """
    Extrahuje text z PDF dokumentu.
    pdf_b64: obsah PDF souboru zakodovany v base64
    Vraci extrahovany text jako plain string.
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("Chybi knihovna 'pypdf'. Nainstalujte: pip install pypdf") from e

    pdf_bytes = base64.b64decode(pdf_b64)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)
