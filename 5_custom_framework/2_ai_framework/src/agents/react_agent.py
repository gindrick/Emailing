import json
from typing import Any, Dict, List, Optional
from .base import Agent, AgentResponse
from ..clients import LLMClient, MCPClient


class ReActAgent(Agent):
    """ReAct (Reason and Act) Agent implementation using MCP tools."""

    def __init__(
        self,
        name: str = "ReAct Agent",
        model: str = "oai-gpt-4.1-nano",
    ):
        super().__init__(name)
        self.llm = LLMClient(llm_model=model)
        self.mcp_client = MCPClient()
        self.max_iterations = 10
        self._connected = False

    async def connect(self):
        """Connect to the MCP tools server."""
        if not self._connected:
            await self.mcp_client.connect()
            self._connected = True

    async def disconnect(self):
        """Disconnect from the MCP tools server."""
        if self._connected:
            await self.mcp_client.disconnect()
            self._connected = False

    async def execute(self, task: str) -> AgentResponse:
        """Execute a task using ReAct pattern with MCP tools."""
        # Ensure we're connected
        await self.connect()

        actions_taken = []
        reasoning_steps = []

        # Get available tools from MCP server
        try:
            tool_schemas = await self.mcp_client.get_tools_definitions()
        except Exception as e:
            return AgentResponse(
                success=False,
                result=None,
                reasoning="Failed to get tools from MCP server",
                actions_taken=actions_taken,
                error=str(e),
            )

        # Build system prompt and add to history if this is the first message
        if not self.conversation_history:
            system_prompt = self._build_system_prompt()
            self.add_to_history({"role": "system", "content": system_prompt})

        # Add user message
        self.add_to_history({"role": "user", "content": task})

        for iteration in range(self.max_iterations):
            try:

                print(f"\n--- Iteration {iteration + 1} ---")
                print("Current conversation history:")
                for msg in self.conversation_history:
                    print(msg)
                print("--------------------------------------")

                # Call LLM with tools
                response = await self.llm.call(
                    messages=self.conversation_history,
                    tools=tool_schemas,
                )

                # Check if the response contains tool calls
                message = response.choices[0].message

                print(f"\n--- Iteration {iteration + 1} ---")
                print(f"LLM Response:")
                print(message)
                print(message.model_dump())
                print("--------------------------------------")

                # First check if there's any content (reasoning) before tool calls
                if message.content:
                    print(f"Assistant reasoning: {message.content}")

                if message.tool_calls:
                    tool_call_msg = {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                            for tool_call in message.tool_calls
                        ],
                    }

                    self.add_to_history(tool_call_msg)

                    # Execute each tool call via MCP
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)

                        reasoning_steps.append(f"Using tool: {tool_name}")

                        try:
                            # Call tool via MCP
                            tool_result = await self.mcp_client.call_tool(
                                tool_name, tool_args
                            )
                            actions_taken.append(f"{tool_name}({tool_args})")

                            # Add tool result to conversation
                            tool_message = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(tool_result),  # Ensure it's a string
                            }

                            print("--- Tool Result ---")
                            print(f"Tool: {tool_name}({tool_args})")
                            print(f"Result: {tool_result}")
                            print("---------------------")

                            self.add_to_history(tool_message)

                        except Exception as e:
                            error_msg = f"Tool execution error: {str(e)}"
                            return AgentResponse(
                                success=False,
                                result=None,
                                reasoning=" -> ".join(reasoning_steps),
                                actions_taken=actions_taken,
                                error=error_msg,
                            )
                else:
                    # No tool calls, we have the final answer
                    content = message.content or ""
                    self.add_to_history({"role": "assistant", "content": content})
                    reasoning_steps.append("Generated final response")

                    return AgentResponse(
                        success=True,
                        result=content,
                        reasoning=" -> ".join(reasoning_steps),
                        actions_taken=actions_taken,
                    )

            except Exception as e:
                return AgentResponse(
                    success=False,
                    result=None,
                    reasoning=" -> ".join(reasoning_steps),
                    actions_taken=actions_taken,
                    error=f"LLM error: {str(e)}",
                )

        # Max iterations reached
        return AgentResponse(
            success=False,
            result=None,
            reasoning=" -> ".join(reasoning_steps),
            actions_taken=actions_taken,
            error="Max iterations reached without completing the task",
        )

    def _build_system_prompt(self) -> str:
        """Build the system prompt for ReAct pattern."""
        return """You are an AI assistant that follows the ReAct (Reason + Act) pattern.

For each step:
1. Reason: Think about what needs to be done next
2. Act: Use the appropriate tool to take action
3. Observe: Consider the tool's output

Continue this cycle until the task is complete. When you have achieved the goal, provide a final answer without using any more tools.

Important: Once you have all the information needed to answer the user's request, stop using tools and provide your final response."""

    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, "_connected") and self._connected:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.disconnect())
            finally:
                loop.close()
