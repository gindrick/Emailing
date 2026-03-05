#!/usr/bin/env python3
"""
Research Agent Example: Scientific Research Analysis
Analyze climate change data and create predictive models.

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
    print("=== Research Agent: Climate Change Scientific Analysis ===")
    print("Analyze climate data and create predictive models\n")
    
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
        
        task = """Conduct a scientific analysis of global temperature trends:
        1. Research current global temperature data and trends
        2. Find information about CO2 levels and their correlation with temperature
        3. Create a Python program to model temperature change over time
        4. Calculate statistical correlations and projections
        5. Generate data representations of the trends (using Python)
        6. Write a scientific summary with conclusions
        
        Save all analysis and code to 'climate_analysis_report.txt'"""
        
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