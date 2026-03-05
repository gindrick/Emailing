import os
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for connecting to MCP server."""

    def __init__(self, server_url: Optional[str] = None):
        # Use environment variable if server_url not provided
        if server_url is None:
            server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8002/mcp")
        self.server_url = server_url.rstrip("/")
        self.session = None
        self._http_cleanup = None
        self._session_cleanup = None

    @asynccontextmanager
    async def _start_http(self):
        async with streamablehttp_client(
            f"{self.server_url}/mcp", auth=None
        ) as streams:
            yield streams

    async def connect(self):
        """Connect to the MCP tools server."""
        try:
            self._http_cleanup = self._start_http()
            read_stream, write_stream, _refresh = await self._http_cleanup.__aenter__()

            self._session_cleanup = ClientSession(read_stream, write_stream)
            self.session = await self._session_cleanup.__aenter__()

            await self.session.initialize()
            logger.info(f"Connected to MCP server at {self.server_url}")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            raise

    async def ping(self):
        """Ping the server to check connection."""
        if not self.session:
            raise RuntimeError("Client not connected.")
        return await self.session.send_ping()

    async def list_tools(self):
        """List all available tools from the server."""
        if not self.session:
            raise RuntimeError("Client not connected.")
        response = await self.session.list_tools()
        return response.tools

    async def call_tool(self, tool_name: str, parameters: dict) -> str:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            parameters: Parameters to pass to the tool

        Returns:
            Tool result as a string
        """
        if not self.session:
            raise RuntimeError("Client not connected.")

        try:
            response = await self.session.call_tool(tool_name, parameters)

            # Extract text content from response
            if response.content:
                # Combine all text content
                text_parts = []
                for content in response.content:
                    if hasattr(content, "text"):
                        text_parts.append(content.text)
                return "\n".join(text_parts)

            return "No response content"

        except Exception as e:
            error_msg = f"Error calling tool '{tool_name}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def get_tools_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions from MCP tools."""
        if not self.session:
            raise RuntimeError("Client not connected.")

        tools = await self.list_tools()
        openai_tools = []

        for tool in tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools

    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self._session_cleanup:
            await self._session_cleanup.__aexit__(None, None, None)
            self._session_cleanup = None
            self.session = None
        if self._http_cleanup:
            await self._http_cleanup.__aexit__(None, None, None)
            self._http_cleanup = None
        logger.info("Disconnected from MCP server")
