# AI Agent Framework with MCP Integration

A comprehensive framework for building AI agents with different architectures and MCP (Model Context Protocol) tool integration.

## Architecture

The framework is organized into modular components:

```
2_ai_framework/
├── src/
│   ├── agents/         # Agent implementations
│   ├── clients/        # LLM and MCP clients
│   └── examples/       # Usage examples organized by agent type
│       ├── react/              # ReAct agent examples
│       ├── plan_execute/       # Plan-Execute agent examples
│       ├── workflow/           # Workflow agent examples
│       └── comparison/         # Agent comparison examples
../1_mcp/               # MCP server providing tools
```

## Setup

### 1. Install Dependencies

```bash
cd 2_ai_framework
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync
```

### 2. Start LiteLLM Proxy

The framework uses LiteLLM to support multiple LLM providers. Start the proxy server:

```bash
cd 0_litellm
docker compose up
```

This will start the proxy on `http://localhost:4000`. You can open LiteLLM UI on `http://localhost:4000/ui`.

### 3. Start MCP Tools Server

```bash
cd ../1_mcp
python server.py
```

The MCP server will run on `http://localhost:8002/mcp`.

### 4. Set Environment Variables

Create a `.env` file in the 2_ai_framework directory:

```env
# LiteLLM Configuration
LITELLM_BASE_URL=http://localhost:4000
LITELLM_API_KEY=sk-1234  # Default key for local LiteLLM proxy

# MCP Server Configuration
MCP_SERVER_URL=http://localhost:8002/mcp
```

Notes:

- The Tavily and Wolfram API keys should be configured in the 1_mcp server's `.env` file, not here.
- The MCPClient automatically reads `MCP_SERVER_URL` from the environment, so you don't need to pass it to agents.

## Available Agents

### 1. ReAct Agent

- **Pattern**: Reason → Act → Observe
- **Best for**: Exploratory tasks, research, iterative problem-solving

### 2. Plan-Execute Agent

- **Pattern**: Plan → Execute → Replan (if needed)
- **Best for**: Complex multi-step tasks, projects requiring structure

### 3. Workflow Agent

- **Pattern**: Follows predefined or dynamic workflows
- **Best for**: Repetitive tasks, process automation, conditional logic

## MCP Tools

All agents use tools via the MCP server, which provides:

- **calculator** - Mathematical calculations
- **web_search** - Web search using Tavily API
- **read_file** - Read file contents
- **write_file** - Write to files
- **list_files** - List directory contents
- **python_repl** - Execute Python code
- **wolfram_alpha** - Query Wolfram Alpha

## Quick Start

```python
import asyncio
from src.agents import ReActAgent

async def main():
    # Create agent (MCPClient automatically reads MCP_SERVER_URL from environment)
    agent = ReActAgent(
        name="Assistant",
        model="gpt-4o-mini"
    )

    # Connect to MCP server
    await agent.connect()

    # Execute task
    result = await agent.execute("Search for Python tutorials and save a summary")
    print(f"Result: {result.result}")

    # Disconnect
    await agent.disconnect()

asyncio.run(main())
```

## Examples

Run any example:

```bash
# ReAct Agent Examples
uv run -m src.examples.react.circle_area_calculation
uv run -m src.examples.react.stock_market_analysis

# Plan-Execute Agent Examples
uv run -m src.examples.plan_execute.multi_file_data_processing
uv run -m src.examples.plan_execute.renewable_energy_market_research

# Workflow Agent Examples
uv run -m src.examples.workflow.simple_linear_workflow
uv run -m src.examples.workflow.data_science_workflow
```

## Agent Types Explained

### 1. ReAct Agent

- **Approach**: Thought-Action-Observation cycles
- **Best for**: Dynamic problem solving, exploration tasks
- **How it works**: Thinks about what to do, takes an action, observes the result, then repeats

### 2. Plan-Execute Agent

- **Approach**: Strategic planning with execution and replanning
- **Best for**: Complex projects, goal-oriented tasks
- **How it works**: Creates a plan, executes steps systematically, replans if failures occur

### 3. Workflow Agent

- **Approach**: Predefined workflows with conditional logic
- **Best for**: Repeated processes, business automation
- **How it works**: Follows predefined node graphs with branching and state management

## Example Output

When you run the examples, you'll see:

- Step-by-step reasoning for each agent
- Actions taken and their results
- Performance comparisons
- Generated files with calculation results

## Educational Value

This project demonstrates:

- Different agent architecture patterns
- OpenAI API integration strategies
- Tool/action abstraction in AI systems
- Various reasoning paradigms (reactive vs. planning)
- State management approaches
- Real-world implementation trade-offs

Each agent type showcases different approaches to autonomous task execution, providing practical insights into AI agent design decisions without the complexity of existing frameworks.
