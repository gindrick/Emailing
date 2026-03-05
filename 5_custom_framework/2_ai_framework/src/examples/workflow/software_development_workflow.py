#!/usr/bin/env python3
"""
Advanced Workflow Agent Example: Software Development Lifecycle
Execute a complete software development workflow with testing and documentation.

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


def create_software_development_workflow():
    """Create a software development workflow with testing and deployment."""
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start Development",
                "description": "Begin software development process",
                "next": ["requirements"],
                "data": {},
            },
            {
                "id": "requirements",
                "type": "task",
                "name": "Gather Requirements",
                "description": "Research best practices for building a REST API with Python",
                "data": {"output_var": "requirements"},
                "next": ["design"],
            },
            {
                "id": "design",
                "type": "task",
                "name": "Design Architecture",
                "description": "Create architectural design and save to 'api_design.txt'",
                "data": {},
                "next": ["implement"],
            },
            {
                "id": "implement",
                "type": "task",
                "name": "Implement Code",
                "description": "Generate Python code for a sample REST API with FastAPI",
                "data": {"output_var": "api_code"},
                "next": ["test"],
            },
            {
                "id": "test",
                "type": "task",
                "name": "Create Tests",
                "description": "Generate unit tests for the API code",
                "data": {"output_var": "test_code"},
                "next": ["validate"],
            },
            {
                "id": "validate",
                "type": "condition",
                "name": "Validate Quality",
                "description": "Check if code meets quality standards",
                "condition": "code has proper structure and tests",
                "next": ["document", "refactor"],
                "data": {},
            },
            {
                "id": "refactor",
                "type": "task",
                "name": "Refactor Code",
                "description": "Improve code quality and add error handling",
                "data": {},
                "next": ["document"],
            },
            {
                "id": "document",
                "type": "task",
                "name": "Generate Documentation",
                "description": "Create comprehensive documentation and save to 'api_documentation.txt'",
                "data": {},
                "next": ["deployment_guide"],
            },
            {
                "id": "deployment_guide",
                "type": "task",
                "name": "Create Deployment Guide",
                "description": "Generate deployment instructions for Docker and Kubernetes",
                "data": {},
                "next": ["end"],
            },
            {
                "id": "end",
                "type": "end",
                "name": "Complete",
                "description": "Software development workflow completed",
                "next": [],
                "data": {},
            },
        ]
    }


async def main():
    print("=== Advanced Workflow: Software Development Lifecycle ===")
    print("Execute a complete software development workflow\n")
    print(
        "This workflow includes: requirements → design → implementation → testing → validation → documentation\n"
    )

    # Create agent with MCP tools
    agent = WorkflowAgent(name="Advanced Workflow Assistant", model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        # Build and execute the software development workflow
        workflow = create_software_development_workflow()
        agent.build_workflow(workflow)

        task = "Execute the software development workflow to create a REST API"

        result = await agent.execute(task)
        print(f"\nSuccess: {result.success}")
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
        print(
            "Error: Please set either LITELLM_API_KEY or OPENAI_API_KEY environment variable"
        )
        import sys

        sys.exit(1)

    asyncio.run(main())
