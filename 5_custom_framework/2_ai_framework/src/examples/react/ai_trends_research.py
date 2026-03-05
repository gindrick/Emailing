#!/usr/bin/env python3
"""
ReAct Agent Example: Web Search and Analysis
Research current AI trends and create a summary.

Prerequisites:
1. Start the MCP tools server:
   cd mcp_tools_server
   uv run uvicorn server:app --port 8002

2. Set environment variables:
   - LITELLM_API_KEY or OPENAI_API_KEY
"""

import asyncio
import os
from dotenv import load_dotenv
from ...agents import ReActAgent

load_dotenv()


async def main():
    print("=== ReAct Agent: AI Trends Research ===")
    print("Research current AI trends and create a summary\n")

    # Create agent with MCP tools
    agent = ReActAgent(
        name="ReAct Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Search for the latest trends in artificial intelligence in 2024.
        Create a summary file 'ai_trends_2024.txt' with:
        1. Top 3 trends you found
        2. A brief description of each trend
        3. Why these trends are significant"""

        result = await agent.execute(task)
        print(f"Success: {result.success}")
        print(f"Result: {result.result}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Actions taken: {result.actions_taken}")
        if result.error:
            print(f"Error: {result.error}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Disconnect from MCP server
        await agent.disconnect()
        print("\nDisconnected from MCP server")


if __name__ == "__main__":
    # Check for LLM API key
    if not os.getenv("LITELLM_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("Error: Please set either LITELLM_API_KEY or OPENAI_API_KEY environment variable")
        import sys
        sys.exit(1)
    
    asyncio.run(main())