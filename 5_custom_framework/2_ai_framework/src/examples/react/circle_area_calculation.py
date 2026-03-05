#!/usr/bin/env python3
"""
ReAct Agent Example: Mathematical Calculation
Calculate the area of a circle and save to file.

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
    print("=== ReAct Agent: Circle Area Calculation ===")
    print("Calculate the area of a circle with radius 5 and save the result to a file\n")

    # Create agent with MCP tools
    agent = ReActAgent(
        name="ReAct Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = "Calculate the area of a circle with radius 5 (use π ≈ 3.14159) and save the result to a file called 'circle_area.txt'"

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
    asyncio.run(main())