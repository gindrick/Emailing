#!/usr/bin/env python3
"""
Advanced Workflow Agent Example: Data Science Research Workflow
Execute a comprehensive data science analysis with conditional branching.

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


def create_data_science_workflow():
    """Create a complex data science research workflow."""
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start Data Science Project",
                "description": "Begin comprehensive data science analysis",
                "next": ["research_phase"],
                "data": {},
            },
            {
                "id": "research_phase",
                "type": "task",
                "name": "Research Phase",
                "description": "Research machine learning applications in healthcare using web search",
                "data": {"output_var": "research_results"},
                "next": ["data_analysis"],
            },
            {
                "id": "data_analysis",
                "type": "task",
                "name": "Data Analysis",
                "description": "Create Python code to analyze the research findings and generate statistical insights",
                "data": {"output_var": "analysis_results"},
                "next": ["check_quality"],
            },
            {
                "id": "check_quality",
                "type": "condition",
                "name": "Quality Check",
                "description": "Check if the analysis produced meaningful results",
                "condition": "analysis results contain valid statistical data",
                "next": ["generate_report", "enhance_analysis"],
                "data": {},
            },
            {
                "id": "enhance_analysis",
                "type": "task",
                "name": "Enhance Analysis",
                "description": "Use Wolfram Alpha to get additional computational insights and mathematical analysis",
                "data": {"output_var": "enhanced_results"},
                "next": ["generate_report"],
            },
            {
                "id": "generate_report",
                "type": "task",
                "name": "Generate Report",
                "description": "Create a comprehensive report combining all findings and save to 'data_science_report.txt'",
                "data": {},
                "next": ["visualization"],
            },
            {
                "id": "visualization",
                "type": "task",
                "name": "Create Visualizations",
                "description": "Generate Python code for data visualization using matplotlib",
                "data": {"output_var": "visualization_code"},
                "next": ["save_artifacts"],
            },
            {
                "id": "save_artifacts",
                "type": "task",
                "name": "Save All Artifacts",
                "description": "Save visualization code to 'visualizations.py' and update the report",
                "data": {},
                "next": ["end"],
            },
            {
                "id": "end",
                "type": "end",
                "name": "Complete",
                "description": "Data science workflow completed",
                "next": [],
                "data": {},
            },
        ]
    }


async def main():
    print("=== Advanced Workflow: Data Science Research ===")
    print("Execute a comprehensive data science analysis workflow\n")
    print(
        "This workflow includes: research → analysis → quality check → reporting → visualization\n"
    )

    # Create agent with MCP tools
    agent = WorkflowAgent(name="Advanced Workflow Assistant", model="oai-gpt-4.1-nano")

    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        # Build and execute the data science workflow
        workflow = create_data_science_workflow()
        agent.build_workflow(workflow)

        task = "Execute the data science workflow to analyze machine learning applications in healthcare"

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
