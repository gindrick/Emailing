#!/usr/bin/env python3
"""
Workflow Agent Example: Dynamic Workflow Generation
Let the agent create its own workflow based on task requirements.

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
from ...agents import WorkflowAgent, WorkflowNode, NodeType

load_dotenv()


async def main():
    print("=== Workflow Agent: Dynamic Workflow Generation ===")
    print("Let the agent create its own workflow for data analysis\n")

    # Create agent with MCP tools
    agent = WorkflowAgent(
        name="Workflow Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        # Clear existing workflow to force dynamic creation
        agent.workflow_nodes.clear()

        task = """Create a data analysis workflow that:
        1. Fetches population data for major cities
        2. Calculates statistics
        3. Creates visualizations (as Python code)
        4. Generates a report
        Execute this workflow to analyze urban population trends."""

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