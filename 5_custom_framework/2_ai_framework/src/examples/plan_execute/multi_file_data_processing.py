#!/usr/bin/env python3
"""
Plan-Execute Agent Example: Multi-file Data Processing
Create and process multiple data files with calculations.

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
from ...agents import PlanExecuteAgent

load_dotenv()


async def main():
    print("=== Plan-Execute Agent: Multi-file Data Processing ===")
    print("Create and process multiple data files with calculations\n")

    # Create agent with MCP tools
    agent = PlanExecuteAgent(
        name="Plan-Execute Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Perform a multi-step data processing task:
        1. Create a file 'data1.txt' with numbers: 10, 20, 30, 40, 50
        2. Create a file 'data2.txt' with numbers: 5, 15, 25, 35, 45
        3. Read both files and calculate the sum of all numbers
        4. Calculate the average of all numbers
        5. Create a summary file 'summary.txt' with the results

        Make sure to handle each step carefully and verify the results."""

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