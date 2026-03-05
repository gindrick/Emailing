#!/usr/bin/env python3
"""
Workflow Agent Example: Data Flow Demonstration
Shows how data flows between nodes using variables.

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
from ...agents import WorkflowAgent

load_dotenv()


def create_data_flow_workflow():
    """Create a workflow that demonstrates data flow between nodes."""
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start",
                "description": "Begin data flow demonstration",
                "next": ["gather_info"],
                "data": {},
            },
            {
                "id": "gather_info",
                "type": "task",
                "name": "Gather Information",
                "description": "Calculate the area of a circle with radius 5 and store the result",
                "data": {"output_var": "circle_area"},
                "next": ["use_previous_data"],
            },
            {
                "id": "use_previous_data",
                "type": "task",
                "name": "Use Previous Data",
                "description": "Using the circle_area from the previous step, calculate the volume of a sphere with the same radius. The area was stored in variable 'circle_area'.",
                "data": {"output_var": "sphere_volume"},
                "next": ["create_summary"],
            },
            {
                "id": "create_summary",
                "type": "task",
                "name": "Create Summary",
                "description": "Create a summary file 'geometry_calculations.txt' that includes both the circle area and sphere volume from previous calculations",
                "data": {},
                "next": ["check_results"],
            },
            {
                "id": "check_results",
                "type": "condition",
                "name": "Check Results",
                "description": "Verify that both calculations were performed correctly",
                "condition": "both circle_area and sphere_volume variables contain valid numeric values",
                "next": ["success", "failure"],
                "data": {},
            },
            {
                "id": "success",
                "type": "task",
                "name": "Report Success",
                "description": "Log success message with all calculated values",
                "data": {},
                "next": ["end"],
            },
            {
                "id": "failure",
                "type": "task",
                "name": "Report Failure",
                "description": "Log what went wrong",
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
    print("=== Workflow Data Flow Demonstration ===")
    print("Shows how data flows between workflow nodes using variables\n")

    # Create agent with MCP tools
    agent = WorkflowAgent(name="Data Flow Demo Agent", model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        # Build and execute the workflow
        workflow = create_data_flow_workflow()
        agent.build_workflow(workflow)

        task = "Execute the workflow to demonstrate data flow between nodes"

        result = await agent.execute(task)
        print(f"\nSuccess: {result.success}")
        print(f"Result: {result.result}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Actions taken: {result.actions_taken}")

        # Show final workflow variables
        print("\nFinal workflow variables:")
        for var_name, var_value in agent.workflow_state.variables.items():
            print(f"  {var_name}: {var_value}")

        if result.error:
            print(f"Error: {result.error}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Disconnect from MCP server
        await agent.disconnect()
        print("\nDisconnected from MCP server")


if __name__ == "__main__":
    # Check for LLM API key
    if not os.getenv("LITELLM_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print(
            "Error: Please set either LITELLM_API_KEY or OPENAI_API_KEY environment variable"
        )
        import sys

        sys.exit(1)

    asyncio.run(main())
