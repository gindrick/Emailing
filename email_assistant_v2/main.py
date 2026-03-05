"""
Email Assistant v2 - Vstupni bod
Spusteni: uv run python main.py

Predpoklady:
  1. docker-compose up -d          (LiteLLM proxy)
  2. uv run python src/mcp_server/server.py  (MCP server)
  3. uv run python main.py         (Workflow Agent)
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.settings import AgentSettings
from src.agents.email_workflow_agent import EmailWorkflowAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main() -> int:
    settings = AgentSettings.from_env()

    logger.info(f"LiteLLM: {settings.litellm_base_url} | Model: {settings.litellm_model}")
    logger.info(f"MCP Server: {settings.mcp_server_url}")
    logger.info(f"Test mode: {settings.test_mode}")
    if settings.test_mode:
        logger.info(f"Test recipient: {settings.test_recipient_email}")

    agent = EmailWorkflowAgent(settings)

    try:
        stats = await agent.run()
    except Exception as e:
        logger.error(f"Workflow selhal: {e}", exc_info=True)
        return 1

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
