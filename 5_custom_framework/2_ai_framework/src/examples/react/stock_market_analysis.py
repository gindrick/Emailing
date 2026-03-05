#!/usr/bin/env python3
"""
Enhanced ReAct Agent Example: Combined Analysis - Stock Market Research
Research a tech company and analyze its stock using multiple tools.

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
    print("=== Enhanced ReAct Agent: Stock Market Analysis ===")
    print("Comprehensive analysis of Microsoft (MSFT) stock\n")

    # Create agent with MCP tools
    agent = ReActAgent(
        name="Enhanced ReAct Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Perform a comprehensive analysis:
        1. Search for recent news about Microsoft (MSFT)
        2. Use Wolfram Alpha to get current stock price and market cap
        3. Write a Python script to calculate P/E ratio if you can find earnings data
        4. Create a summary report in 'msft_analysis.txt' with:
           - Recent news highlights
           - Current financial metrics
           - Your calculated values
           - A brief investment outlook based on the data"""

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