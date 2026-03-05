from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class DocumentExtraction(BaseModel):
    """Strukturovany vystup LLM extrakce z PDF dokumentu."""

    bill_to_customer_id: Optional[str] = Field(
        default=None,
        description=(
            "Zakaznicke ID extraktovane z sekce 'Bill To' / 'Bill-To' v dokumentu. "
            "Vrat None pokud pole neni v dokumentu nalezeno."
        ),
    )
    salutation: str = Field(
        description=(
            "Ceske osloveni pro email. "
            "Pokud je nalezene jmeno fyzicke osoby - muze byt 'Vazeny pane Novak,' nebo 'Vazena pani Novakova,'. "
            "Pokud je to firma nebo nejde urcit - vrat 'Dobry den,'."
        ),
    )
    is_person: bool = Field(
        default=False,
        description="True pokud bylo nalezeno jmeno fyzicke osoby, False pokud firma nebo neznamop.",
    )
