#!/usr/bin/env python3
"""
Advanced Workflow Agent Example: Dynamic E-commerce Recommendation System
Let the agent create its own workflow for building a recommendation system.

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


async def main():
    print("=== Advanced Workflow: E-commerce Recommendation System ===")
    print("Dynamic workflow generation for a complex task\n")
    
    # Create agent with MCP tools
    agent = WorkflowAgent(
        name="Advanced Workflow Assistant",
        model="oai-gpt-4.1-nano")
    
    try:
        # Connect to MCP server
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")
        
        # Clear existing workflow to force dynamic creation
        agent.workflow_nodes.clear()
        
        task = """Create and execute a workflow for building a complete e-commerce recommendation system that:
        1. Researches current recommendation algorithms
        2. Designs the system architecture
        3. Implements a prototype with Python
        4. Creates test data and scenarios
        5. Evaluates performance metrics
        6. Generates a comprehensive report
        
        Save all outputs to appropriate files."""
        
        result = await agent.execute(task)
        print(f"\nSuccess: {result.success}")
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