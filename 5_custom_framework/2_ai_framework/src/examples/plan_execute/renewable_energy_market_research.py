#!/usr/bin/env python3
"""
Research Agent Example: Comprehensive Market Research
Create a detailed analysis report on renewable energy trends.

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
    print("=== Research Agent: Renewable Energy Market Research ===")
    print("Create a comprehensive research report on renewable energy trends\n")
    
    # Create agent with MCP tools
    agent = PlanExecuteAgent(
        name="Research Assistant",
        model="oai-gpt-4.1-nano",
        max_replans=3  # Allow up to 3 replanning attempts for complex research
    )
    
    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")
        
        task = """Create a comprehensive research report on renewable energy market trends for 2024. 
        The report should include:
        1. Current market size and growth projections
        2. Key technologies and their efficiency rates
        3. Major companies and their market share
        4. Investment trends and government policies
        5. Statistical analysis of the data collected
        6. Future outlook and recommendations
        
        Save the final report as 'renewable_energy_report_2024.txt'"""
        
        result = await agent.execute(task)
        print(f"Success: {result.success}")
        print(f"Result Preview: {result.result[:300]}..." if result.result and len(result.result) > 300 else f"Result: {result.result}")
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