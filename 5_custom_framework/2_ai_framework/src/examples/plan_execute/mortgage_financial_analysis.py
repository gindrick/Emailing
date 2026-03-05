#!/usr/bin/env python3
"""
Plan-Execute Agent Example: Financial Analysis and Reporting
Create a comprehensive mortgage analysis report with multiple calculations.

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
    print("=== Plan-Execute Agent: Mortgage Financial Analysis ===")
    print("Create a comprehensive financial report with mortgage calculations\n")

    # Create agent with MCP tools
    agent = PlanExecuteAgent(name="Plan-Execute Assistant", model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Create a comprehensive financial analysis report that includes:
        1. Calculate monthly payment for a $200,000 mortgage at 4.5% interest for 30 years
        2. Calculate total interest paid over the life of the loan
        3. Calculate how much would be saved if paid off in 15 years instead
        4. Save all calculations and analysis to a file called 'mortgage_analysis.txt'

        Use the formula: M = P[r(1+r)^n]/[(1+r)^n-1] where:
        M = monthly payment, P = principal, r = monthly interest rate, n = number of payments"""

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
