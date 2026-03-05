from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

logger = logging.getLogger(__name__)


class MCPClient:
    """Klient pro pripojeni na MCP server."""

    def __init__(self, server_url: Optional[str] = None):
        if server_url is None:
            server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8002")
        self.server_url = server_url.rstrip("/")
        self.session: Optional[ClientSession] = None
        self._http_cleanup = None
        self._session_cleanup = None

    @asynccontextmanager
    async def _start_http(self):
        async with streamablehttp_client(f"{self.server_url}/mcp", auth=None) as streams:
            yield streams

    async def connect(self) -> None:
        """Pripoji se na MCP server."""
        try:
            self._http_cleanup = self._start_http()
            read_stream, write_stream, _refresh = await self._http_cleanup.__aenter__()
            self._session_cleanup = ClientSession(read_stream, write_stream)
            self.session = await self._session_cleanup.__aenter__()
            await self.session.initialize()
            logger.info(f"Pripojeno na MCP server: {self.server_url}")
        except Exception as e:
            logger.error(f"Nelze se pripojit na MCP server: {e}")
            raise

    async def disconnect(self) -> None:
        """Odpoji se od MCP serveru."""
        if self._session_cleanup:
            await self._session_cleanup.__aexit__(None, None, None)
            self._session_cleanup = None
            self.session = None
        if self._http_cleanup:
            await self._http_cleanup.__aexit__(None, None, None)
            self._http_cleanup = None
        logger.info("Odpojeno od MCP serveru")

    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Zavola nastroj na MCP serveru a vrati textovy vysledek."""
        if not self.session:
            raise RuntimeError("MCP client neni pripojen. Zavolej connect() nejdrive.")

        response = await self.session.call_tool(tool_name, parameters)

        if response.content:
            text_parts = [c.text for c in response.content if hasattr(c, "text")]
            return "\n".join(text_parts)
        return ""

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Vrati seznam dostupnych nastroju jako OpenAI tool definitions."""
        if not self.session:
            raise RuntimeError("MCP client neni pripojen.")

        response = await self.session.list_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in response.tools
        ]
