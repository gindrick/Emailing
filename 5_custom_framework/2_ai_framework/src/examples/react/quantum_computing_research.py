#!/usr/bin/env python3
"""
Enhanced ReAct Agent Example: Web Search and Analysis
Research the latest in quantum computing and summarize findings.

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
    print("=== Enhanced ReAct Agent: Quantum Computing Research ===")
    print("Research the latest breakthroughs in quantum computing\n")

    # Create agent with MCP tools
    agent = ReActAgent(
        name="Enhanced ReAct Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Search for the latest breakthroughs in quantum computing in 2024.
        Find at least 3 recent developments and create a summary that includes:
        1. What the breakthrough is
        2. Who achieved it (company/institution)
        3. Why it's significant
        Save your findings to 'quantum_computing_2024.txt'"""

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