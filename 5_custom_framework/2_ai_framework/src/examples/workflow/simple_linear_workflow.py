#!/usr/bin/env python3
"""
Workflow Agent Example: Simple Linear Workflow
Execute a predefined linear workflow for calculations.

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


def create_simple_workflow():
    """Create a simple linear workflow."""
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start",
                "description": "Start the workflow",
                "next": ["task1"],
                "data": {},
            },
            {
                "id": "task1",
                "type": "task",
                "name": "Calculate Square",
                "description": "Calculate the square of 15 using the calculator tool",
                "data": {"output_var": "square_result"},
                "next": ["task2"],
            },
            {
                "id": "task2",
                "type": "task",
                "name": "Save Result",
                "description": "Save the calculation result to a file named 'square_result.txt'",
                "data": {},
                "next": ["end"],
            },
            {
                "id": "end",
                "type": "end",
                "name": "End",
                "description": "Workflow completed",
                "next": [],
                "data": {},
            },
        ]
    }


async def main():
    print("=== Workflow Agent: Simple Linear Workflow ===")
    print("Execute a predefined linear workflow for calculations\n")

    # Create agent with MCP tools
    agent = WorkflowAgent(name="Workflow Assistant", model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        # Build the simple workflow
        simple_workflow = create_simple_workflow()
        agent.build_workflow(simple_workflow)

        result = await agent.execute("Execute the simple calculation workflow")
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
