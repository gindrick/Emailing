"""
BaseAgent - zakladni trida pro vsechny specializovane agenty.

Poskytuje:
- Filtraci nastroju podle TOOL_WHITELIST
- Primy volani MCP nastroju (call_tool)
- Sdilenou referenci na MCPClient a LLMClient
"""

from __future__ import annotations

import logging
from typing import Any

from src.clients.llm_client import LLMClient
from src.clients.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Zakladni trida pro specializovane sub-agenty.

    Kazdy agent definuje TOOL_WHITELIST - seznam MCP nastroju, ktere smi pouzivat.
    Volani nastroje mimo whitelist je blokovano (ochrana pred LLM konfuzi).
    """

    TOOL_WHITELIST: list[str] = []

    def __init__(self, mcp: MCPClient, llm: LLMClient) -> None:
        self._mcp = mcp
        self._llm = llm

    async def call_tool(self, name: str, args: dict[str, Any] | None = None) -> str:
        """
        Zavola MCP nastroj. Kontroluje whitelist - pokud je definovan,
        nastroj mimo nej je odmitnut.
        """
        if self.TOOL_WHITELIST and name not in self.TOOL_WHITELIST:
            raise PermissionError(
                f"Agent '{self.__class__.__name__}' nema povolen nastroj '{name}'. "
                f"Povolene nastroje: {self.TOOL_WHITELIST}"
            )
        logger.debug(f"  [{self.__class__.__name__}] call_tool({name})")
        return await self._mcp.call_tool(name, args or {})
