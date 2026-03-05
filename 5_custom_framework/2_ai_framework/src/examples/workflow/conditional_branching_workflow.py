#!/usr/bin/env python3
"""
Workflow Agent Example: Conditional Branching Workflow
Execute a workflow with conditional logic based on results.

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


def create_conditional_workflow():
    """Create a workflow with conditional branching."""
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start",
                "description": "Start conditional workflow",
                "next": ["search_task"],
                "data": {},
            },
            {
                "id": "search_task",
                "type": "task",
                "name": "Search for AI News",
                "description": "Search for recent news about artificial intelligence",
                "data": {"output_var": "search_results"},
                "next": ["check_results"],
            },
            {
                "id": "check_results",
                "type": "condition",
                "name": "Check if results found",
                "description": "Check if search returned meaningful results",
                "condition": "search_results contains relevant information",
                "next": ["process_results", "alternative_search"],
                "data": {},
            },
            {
                "id": "process_results",
                "type": "task",
                "name": "Process Results",
                "description": "Create a summary of the AI news found",
                "data": {},
                "next": ["save_summary"],
            },
            {
                "id": "alternative_search",
                "type": "task",
                "name": "Alternative Search",
                "description": "Try a different search approach using Wolfram Alpha for AI statistics",
                "data": {},
                "next": ["save_summary"],
            },
            {
                "id": "save_summary",
                "type": "task",
                "name": "Save Summary",
                "description": "Save the findings to 'ai_research_summary.txt'",
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
    print("=== Workflow Agent: Conditional Branching ===")
    print("Execute a workflow with conditional logic\n")

    # Create agent with MCP tools
    agent = WorkflowAgent(
        name="Workflow Assistant",
        model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        # Build the conditional workflow
        conditional_workflow = create_conditional_workflow()
        agent.build_workflow(conditional_workflow)

        result = await agent.execute("Research AI and create a summary")
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