# MCP Tools Server

A Model Context Protocol (MCP) server that provides various tools for AI agents to interact with external services and perform computational tasks.

## Overview

This MCP server implements a collection of tools that AI agents can use through the Model Context Protocol. It's built with Python using the MCP SDK, Starlette for HTTP handling, and uvicorn as the ASGI server.

## Available Tools

### 1. **calculator**

- **Description**: Perform mathematical calculations using Python expressions
- **Input**: `expression` (string) - Mathematical expression to evaluate
- **Example**: `{"expression": "2 + 2"}` or `{"expression": "sqrt(16)"}`

### 2. **web_search**

- **Description**: Search the web using Tavily API
- **Input**: `query` (string) - Search query
- **Requires**: `TAVILY_API_KEY` environment variable
- **Example**: `{"query": "latest AI developments"}`

### 3. **read_file**

- **Description**: Read contents of a file
- **Input**: `path` (string) - File path to read
- **Example**: `{"path": "./example.txt"}`

### 4. **write_file**

- **Description**: Write content to a file
- **Input**:
  - `path` (string) - File path to write to
  - `content` (string) - Content to write
- **Example**: `{"path": "./output.txt", "content": "Hello, World!"}`

### 5. **list_files**

- **Description**: List files in a directory
- **Input**: `path` (string) - Directory path
- **Example**: `{"path": "./"}`

### 6. **python_repl**

- **Description**: Execute Python code in a sandboxed environment
- **Input**: `code` (string) - Python code to execute
- **Example**: `{"code": "print('Hello from Python!')"}`

### 7. **wolfram_alpha**

- **Description**: Query Wolfram Alpha for computational knowledge
- **Input**: `query` (string) - Query for Wolfram Alpha
- **Requires**: `WOLFRAM_APP_ID` environment variable
- **Example**: `{"query": "integrate x^2 dx"}`
- **Note**: Real-time financial data (stock prices, market cap) may show as "data not available" in the free API tier. Works well for math, science, geography, and general knowledge queries.

## Project Structure

```
1_mcp/
├── README.md           # This file
├── pyproject.toml      # Project dependencies and metadata
├── server.py           # Main MCP server implementation
├── uv.lock            # Locked dependencies
└── tools/             # Tool implementations
    ├── __init__.py
    ├── calculator.py   # Mathematical calculations
    ├── file_operations.py  # File I/O operations
    ├── python_repl.py  # Python code execution
    ├── web_search.py   # Web search via Tavily
    └── wolfram.py      # Wolfram Alpha integration
```

## Setup

### 1. Install Dependencies

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Required for web search functionality
TAVILY_API_KEY=your_tavily_api_key_here

# Required for Wolfram Alpha functionality
WOLFRAM_APP_ID=your_wolfram_app_id_here
```

## Running the Server

Start the MCP server:

```bash
python server.py
```

The server will be available at `http://localhost:8002`

### Alternative: Run with UV

```bash
uv run server.py
```

## API Endpoints

- `POST /mcp` - MCP message endpoint using StreamableHTTP for message handling

## Development

### Adding New Tools

1. Create a new Python file in the `tools/` directory
2. Implement your tool function with appropriate error handling
3. Import and register the tool in `server.py`
4. Add the tool definition to the `handle_list_tools()` function

### Testing Tools Individually

Each tool can be tested independently:

```python
# Test calculator
from tools.calculator import calculate
result = await calculate("2 + 2")
print(result)  # Output: 4

# Test file operations
from tools.file_operations import read_file
content = await read_file("test.txt")
print(content)
```

## Security Considerations

- The `python_repl` tool executes arbitrary Python code - use with caution
- File operations are restricted to the server's file system access
- API keys should be kept secure and never committed to version control

## Troubleshooting

### Common Issues

1. **Server won't start**: Ensure all dependencies are installed with `uv sync`
2. **Web search not working**: Check that `TAVILY_API_KEY` is set correctly
3. **Wolfram Alpha errors**: Verify `WOLFRAM_APP_ID` is valid
4. **Connection refused**: Make sure the server is running and the port is correct
