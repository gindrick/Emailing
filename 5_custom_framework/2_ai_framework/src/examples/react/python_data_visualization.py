#!/usr/bin/env python3
"""
Enhanced ReAct Agent Example: Python Code Generation and Execution
Create and run a data visualization script.

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
    print("=== Enhanced ReAct Agent: Python Data Visualization ===")
    print("Create and execute a data visualization script\n")

    # Create agent with MCP tools
    agent = ReActAgent(
        name="Enhanced ReAct Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Create a Python script that:
        1. Generates sample data for a sine wave and cosine wave
        2. Creates a matplotlib plot showing both waves
        3. Adds proper labels, title, and legend
        4. Saves the plot as 'wave_comparison.png'
        5. Also saves the script itself as 'wave_plot.py'
        Execute the script and verify it works correctly."""

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