import json
import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from .base import Agent, AgentResponse
from ..clients import LLMClient, MCPClient
from .workflow_models import WorkflowTaskOutput, WorkflowConditionOutput

# Configure logger with custom formatting to remove the logger name prefix
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(message)s')  # Only show the message, no prefix
handler.setFormatter(formatter)
logger.handlers = []  # Remove any existing handlers
logger.addHandler(handler)
logger.propagate = False  # Don't propagate to parent loggers


class NodeType(Enum):
    """Types of workflow nodes."""

    START = "start"
    TASK = "task"
    CONDITION = "condition"
    PARALLEL = "parallel"
    END = "end"


@dataclass
class WorkflowNode:
    """A node in the workflow."""

    id: str
    type: NodeType
    name: str
    description: str
    data: Dict[str, Any]
    next_nodes: List[str]
    condition: Optional[str] = None


@dataclass
class WorkflowState:
    """Current state of workflow execution."""

    current_nodes: List[str]
    completed_nodes: List[str]
    node_results: Dict[str, Any]
    variables: Dict[str, Any]
    is_complete: bool = False


class WorkflowAgent(Agent):
    """Custom Advanced Workflow Agent with complex multi-step workflow management using MCP tools."""

    def __init__(
        self,
        name: str = "Workflow Agent",
        model: str = "oai-gpt-4.1-nano",
    ):
        super().__init__(name)
        self.llm = LLMClient(llm_model=model)
        self.mcp_client = MCPClient()
        self.workflow_nodes: Dict[str, WorkflowNode] = {}
        self.workflow_state: Optional[WorkflowState] = None
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

    def add_node(self, node: WorkflowNode):
        """Add a node to the workflow."""
        self.workflow_nodes[node.id] = node

    def build_workflow(self, workflow_definition: Dict[str, Any]):
        """Build workflow from a definition."""
        # Clear existing workflow
        self.workflow_nodes.clear()
        
        logger.info("📊 Building workflow...")
        logger.info(f"   Total nodes: {len(workflow_definition.get('nodes', []))}")

        # Parse nodes
        for node_data in workflow_definition.get("nodes", []):
            node = WorkflowNode(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                name=node_data["name"],
                description=node_data.get("description", ""),
                data=node_data.get("data", {}),
                next_nodes=node_data.get("next", []),
                condition=node_data.get("condition"),
            )
            self.add_node(node)
            
            # Log node details
            logger.info(f"   Added node: {node.id} ({node.type.value})")
            logger.info(f"      Name: {node.name}")
            logger.info(f"      Next: {node.next_nodes}")
            if node.data:
                logger.info(f"      Data: {node.data}")
            if node.condition:
                logger.info(f"      Condition: {node.condition}")
        
        logger.info("✅ Workflow built successfully\n")

    async def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """Execute the workflow."""
        # Ensure we're connected
        await self.connect()

        actions_taken = []
        reasoning_steps = []

        try:
            logger.info("🚀 Starting workflow execution")
            logger.info(f"   Task: {task}")
            if context:
                logger.info(f"   Initial context: {context}")
            
            # Initialize workflow state
            self.workflow_state = WorkflowState(
                current_nodes=["start"],
                completed_nodes=[],
                node_results={},
                variables=context or {},
            )
            logger.info("   Initial state: starting from 'start' node\n")

            # If no workflow is defined, build one dynamically
            if not self.workflow_nodes:
                reasoning_steps.append(
                    "No predefined workflow, building one dynamically"
                )
                workflow_def = await self._build_dynamic_workflow(task)

                print(" ---- Dynamic Workflow Definition ----")
                print(json.dumps(workflow_def, indent=2))
                print(" --------------------------------------")

                if not workflow_def:
                    return AgentResponse(
                        success=False,
                        result=None,
                        reasoning=" -> ".join(reasoning_steps),
                        actions_taken=actions_taken,
                        error="Failed to build workflow",
                    )

                self.build_workflow(workflow_def)
                actions_taken.append("Built dynamic workflow")

            # Execute workflow
            logger.info("🔄 Starting workflow execution loop...")
            while not self.workflow_state.is_complete:
                current_nodes = self.workflow_state.current_nodes.copy()

                if not current_nodes:
                    reasoning_steps.append("No more nodes to execute")
                    logger.info("   No more nodes to execute - workflow complete")
                    break

                logger.info(f"\n📍 Current nodes: {current_nodes}")
                logger.info(f"   Completed nodes: {self.workflow_state.completed_nodes}")
                logger.info(f"   Current variables: {json.dumps(self.workflow_state.variables, indent=2)}")

                # Handle parallel execution
                if len(current_nodes) > 1:
                    reasoning_steps.append(
                        f"Executing {len(current_nodes)} nodes in parallel"
                    )
                    logger.info(f"   ⚡ Executing {len(current_nodes)} nodes in parallel")
                    results = await self._execute_parallel_nodes(current_nodes)

                    for node_id, result in results.items():
                        self.workflow_state.node_results[node_id] = result
                        self.workflow_state.completed_nodes.append(node_id)
                        actions_taken.append(f"Completed node: {node_id}")
                        logger.info(f"   ✅ Completed parallel node: {node_id}")
                else:
                    # Execute single node
                    node_id = current_nodes[0]
                    node = self.workflow_nodes.get(node_id)

                    if not node:
                        return AgentResponse(
                            success=False,
                            result=None,
                            reasoning=" -> ".join(reasoning_steps),
                            actions_taken=actions_taken,
                            error=f"Node {node_id} not found",
                        )

                    reasoning_steps.append(f"Executing node: {node.name}")
                    logger.info(f"\n🎯 Executing node: {node_id}")
                    logger.info(f"   Type: {node.type.value}")
                    logger.info(f"   Name: {node.name}")
                    logger.info(f"   Description: {node.description}")
                    
                    result = await self._execute_node(node)
                    
                    logger.info(f"\n✅ Node {node_id} completed")
                    logger.info(f"   Result: {json.dumps(result, indent=2)}")

                    self.workflow_state.node_results[node_id] = result
                    self.workflow_state.completed_nodes.append(node_id)
                    actions_taken.append(f"Completed: {node.name}")

                # Determine next nodes
                next_nodes = await self._determine_next_nodes(current_nodes)
                self.workflow_state.current_nodes = next_nodes
                
                logger.info(f"\n➡️  Next nodes: {next_nodes}")

                # Check if we reached end
                if "end" in next_nodes or not next_nodes:
                    self.workflow_state.is_complete = True
                    logger.info("   🏁 Reached end of workflow")

            # Synthesize final result
            reasoning_steps.append("Workflow completed, synthesizing results")
            logger.info("\n📊 Workflow execution complete. Synthesizing results...")
            logger.info(f"   Total nodes executed: {len(self.workflow_state.completed_nodes)}")
            logger.info(f"   Final variables: {json.dumps(self.workflow_state.variables, indent=2)}")
            
            final_result = await self._synthesize_workflow_results(task)
            logger.info(f"\n✨ Final synthesized result: {final_result[:200]}..." if len(final_result) > 200 else f"\n✨ Final synthesized result: {final_result}")

            return AgentResponse(
                success=True,
                result=final_result,
                reasoning=" -> ".join(reasoning_steps),
                actions_taken=actions_taken,
            )

        except Exception as e:
            return AgentResponse(
                success=False,
                result=None,
                reasoning=" -> ".join(reasoning_steps),
                actions_taken=actions_taken,
                error=f"Workflow execution error: {str(e)}",
            )

    async def _build_dynamic_workflow(self, task: str) -> Optional[Dict[str, Any]]:
        """Build a workflow dynamically based on the task."""
        prompt = f"""Create a workflow to accomplish this task: {task}

Design a workflow with nodes that represent different steps. Each node should have:
- id: unique identifier
- type: one of ["start", "task", "condition", "parallel", "end"]
- name: short descriptive name
- description: what this node does
- next: list of next node IDs
- data: any additional data needed
- condition: (optional) for condition nodes

Respond in JSON format:
{{
    "nodes": [
        {{
            "id": "start",
            "type": "start",
            "name": "Start",
            "description": "Workflow start",
            "next": ["node1"],
            "data": {{}}
        }},
        ...
    ]
}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm.call(messages)

            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Workflow building error: {e}")
            return None

    async def _execute_node(self, node: WorkflowNode) -> Dict[str, Any]:
        """Execute a single workflow node."""
        logger.info(f"\n🔧 _execute_node called for: {node.id}")
        if node.type == NodeType.START:
            return {"status": "started"}

        elif node.type == NodeType.END:
            return {"status": "completed"}

        elif node.type == NodeType.TASK:
            # Get available tools
            try:
                tool_schemas = await self.mcp_client.get_tools_definitions()
            except Exception as e:
                return {"error": f"Failed to get tools: {str(e)}"}

            # Execute task with tools
            logger.info("   📋 Preparing task context...")
            logger.info(f"   Available variables: {list(self.workflow_state.variables.keys())}")
            logger.info(f"   Previous nodes completed: {list(self.workflow_state.node_results.keys())}")
            
            context_str = f"Current workflow state:\n{json.dumps(self.workflow_state.variables, indent=2)}\n"
            context_str += f"Previous results:\n{json.dumps(self.workflow_state.node_results, indent=2)}\n"

            # Check if node.data specifies output variables
            output_vars_prompt = ""
            if node.data.get("output_var"):
                output_vars_prompt = f"\n\nStore the main result in the variable: {node.data['output_var']}"
            
            task_prompt = f"""{context_str}

Execute this task: {node.description}
Additional data: {json.dumps(node.data)}

Use available tools to complete this task.{output_vars_prompt}

You must provide:
1. A result describing what was accomplished
2. Any variables that should be stored for use by subsequent nodes"""

            messages = [
                {
                    "role": "system",
                    "content": "You are executing a workflow task. Use tools as needed. Return structured output with result and variables.",
                },
                {"role": "user", "content": task_prompt},
            ]

            # Execute with tool use
            for _ in range(3):  # Max attempts
                response = await self.llm.call(messages=messages, tools=tool_schemas)

                message = response.choices[0].message
                if message.tool_calls:
                    # Add the message directly - it's already in the correct format
                    messages.append(message.model_dump())

                    # Then execute each tool and add tool responses
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        
                        logger.info(f"   🔨 Calling tool: {tool_name}")
                        logger.info(f"      Args: {json.dumps(tool_args, indent=2)}")

                        result = await self.mcp_client.call_tool(tool_name, tool_args)
                        
                        logger.info(f"   📤 Tool result: {str(result)[:200]}...")

                        # Add tool response with proper format
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result),
                        }
                        messages.append(tool_msg)
                else:
                    # Task completed - get structured output
                    try:
                        # Get structured output from the final response
                        output = await self.llm.call_structured(
                            messages=messages,
                            response_model=WorkflowTaskOutput
                        )
                        
                        # Store variables if specified
                        if output.variables:
                            for var_name, var_value in output.variables.items():
                                self.workflow_state.variables[var_name] = var_value
                                logger.info(f"Stored variable '{var_name}' = {str(var_value)[:100]}")
                        
                        # If node.data specifies output_var, also store the result there
                        if node.data.get("output_var"):
                            self.workflow_state.variables[node.data["output_var"]] = output.result
                            logger.info(f"Stored node result in variable '{node.data['output_var']}'")
                        
                        return {
                            "result": output.result,
                            "status": "completed",
                            "variables": output.variables
                        }
                    except Exception as e:
                        # Fallback to unstructured response
                        logger.warning(f"Failed to get structured output: {e}")
                        return {"result": message.content or "", "status": "completed"}

            return {"error": "Max attempts reached"}

        elif node.type == NodeType.CONDITION:
            # Evaluate condition
            condition_output = await self._evaluate_condition(node)
            
            # Store any variables from condition evaluation
            if condition_output.variables:
                for var_name, var_value in condition_output.variables.items():
                    self.workflow_state.variables[var_name] = var_value
            
            return {
                "condition_met": condition_output.condition_met,
                "reasoning": condition_output.reasoning,
                "status": "evaluated"
            }

        elif node.type == NodeType.PARALLEL:
            # Parallel nodes are handled differently
            return {"status": "parallel_marker"}

        return {"error": f"Unknown node type: {node.type}"}

    async def _execute_parallel_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Execute multiple nodes in parallel."""
        tasks = []

        for node_id in node_ids:
            node = self.workflow_nodes.get(node_id)
            if node:
                tasks.append(self._execute_node(node))

        results = await asyncio.gather(*tasks)

        return {node_id: result for node_id, result in zip(node_ids, results)}

    async def _evaluate_condition(self, node: WorkflowNode) -> WorkflowConditionOutput:
        """Evaluate a condition node."""
        logger.info("   🤔 Evaluating condition...")
        logger.info(f"      Condition: {node.condition}")
        logger.info(f"      Available variables: {list(self.workflow_state.variables.keys())}")
        
        condition_prompt = f"""Evaluate this condition based on the current state:

Condition: {node.condition}
Current variables: {json.dumps(self.workflow_state.variables)}
Previous results: {json.dumps(self.workflow_state.node_results)}

You must:
1. Determine if the condition is met (true) or not (false)
2. Provide reasoning for your decision
3. Optionally store any relevant variables based on the evaluation"""

        messages = [
            {
                "role": "system",
                "content": "You are evaluating a workflow condition. Return structured output with condition result and reasoning."
            },
            {"role": "user", "content": condition_prompt}
        ]
        
        try:
            # Get structured output
            output = await self.llm.call_structured(
                messages=messages,
                response_model=WorkflowConditionOutput
            )
            return output
        except Exception as e:
            # Fallback to simple evaluation
            logger.warning(f"Failed to get structured condition output: {e}")
            response = await self.llm.call(messages)
            result = response.choices[0].message.content.strip().lower() == "true"
            return WorkflowConditionOutput(
                condition_met=result,
                reasoning="Fallback evaluation",
                variables={}
            )

    async def _determine_next_nodes(self, current_nodes: List[str]) -> List[str]:
        """Determine the next nodes to execute."""
        logger.info("\n🔀 Determining next nodes...")
        next_nodes = []

        for node_id in current_nodes:
            node = self.workflow_nodes.get(node_id)
            if not node:
                continue

            logger.info(f"   From node '{node_id}' (type: {node.type.value}):")
            
            if node.type == NodeType.CONDITION:
                # Check condition result
                result = self.workflow_state.node_results.get(node_id, {})
                condition_met = result.get("condition_met", False)
                reasoning = result.get("reasoning", "No reasoning provided")
                
                logger.info(f"      Condition met: {condition_met}")
                logger.info(f"      Reasoning: {reasoning}")

                # Assume first next node is for true, second for false
                if len(node.next_nodes) >= 2:
                    next_node = (
                        node.next_nodes[0] if condition_met else node.next_nodes[1]
                    )
                    next_nodes.append(next_node)
                    logger.info(f"      → Selected path: {next_node} ({'true' if condition_met else 'false'} branch)")
            else:
                # Add all next nodes
                next_nodes.extend(node.next_nodes)
                logger.info(f"      → Next nodes: {node.next_nodes}")

        # Remove duplicates while preserving order
        seen = set()
        unique_next = []
        for node in next_nodes:
            if node not in seen:
                seen.add(node)
                unique_next.append(node)

        return unique_next

    async def _synthesize_workflow_results(self, original_task: str) -> str:
        """Synthesize all workflow results into a final answer."""
        synthesis_prompt = f"""Original task: {original_task}

Workflow execution results:
{json.dumps(self.workflow_state.node_results, indent=2)}

Final variables state:
{json.dumps(self.workflow_state.variables, indent=2)}

Synthesize these results into a comprehensive answer to the original task."""

        messages = [{"role": "user", "content": synthesis_prompt}]
        response = await self.llm.call(messages)

        return response.choices[0].message.content or ""

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
