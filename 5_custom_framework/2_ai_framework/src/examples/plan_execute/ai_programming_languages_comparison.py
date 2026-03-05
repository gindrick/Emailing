#!/usr/bin/env python3
"""
Research Agent Example: Technology Comparison Study
Compare programming languages for AI development.

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
    print("=== Research Agent: AI Programming Languages Comparison ===")
    print("Compare programming languages for AI development\n")

    # Create agent with MCP tools
    agent = PlanExecuteAgent(
        name="Research Assistant",
        model="oai-gpt-4.1-nano",
        max_replans=3,  # Allow up to 3 replanning attempts for complex research
    )

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Create a comprehensive comparison study of programming languages for AI development:
        1. Research the most popular programming languages for AI (Python, R, Julia, etc.)
        2. Find performance benchmarks and ecosystem information
        3. Analyze job market trends and demand for each language
        4. Create Python code to analyze and visualize the comparison data
        5. Calculate scoring metrics for different criteria (performance, ease of use, community, etc.)
        6. Generate a final recommendation report
        
        Save the complete analysis to 'ai_programming_languages_comparison.txt'"""

        result = await agent.execute(task)
        print(f"Success: {result.success}")
        print(
            f"Result Preview: {result.result[:300]}..."
            if result.result and len(result.result) > 300
            else f"Result: {result.result}"
        )
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