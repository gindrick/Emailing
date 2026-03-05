import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from .base import Agent, AgentResponse
from ..clients import LLMClient, MCPClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Plan:
    """Represents a plan with steps."""

    goal: str
    steps: List[str]
    completed_steps: List[bool]

    def is_complete(self) -> bool:
        return all(self.completed_steps)

    def get_next_step(self) -> Optional[int]:
        for i, completed in enumerate(self.completed_steps):
            if not completed:
                return i
        return None


class PlanExecuteAgent(Agent):
    """Plan-Execute Agent with separate Planner, Agent, and Replanner components using MCP tools."""

    def __init__(
        self,
        name: str = "Plan-Execute Agent",
        model: str = "oai-gpt-4.1-nano",
        max_replans: int = 15,
        max_step_attempts: int = 5,
    ):
        super().__init__(name)
        self.llm = LLMClient(llm_model=model)
        self.mcp_client = MCPClient()
        self.current_plan: Optional[Plan] = None
        self.max_replans = max_replans
        self.max_step_attempts = max_step_attempts
        self.step_results: Dict[str, Any] = {}  # Store results from each step
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
        """Execute a task using Plan-Execute pattern."""
        logger.info("\n" + "=" * 80)
        logger.info(f"STARTING PLAN-EXECUTE AGENT FOR TASK: {task}")
        logger.info("=" * 80 + "\n")

        # Ensure we're connected
        await self.connect()

        actions_taken = []
        reasoning_steps = []
        self.step_results = {}  # Clear previous results

        try:
            # Phase 1: Planning
            logger.info("\n📋 PHASE 1: PLANNING")
            logger.info("-" * 40)
            reasoning_steps.append("Planning phase started")
            plan = await self._create_plan(task)

            if not plan:
                return AgentResponse(
                    success=False,
                    result=None,
                    reasoning=" -> ".join(reasoning_steps),
                    actions_taken=actions_taken,
                    error="Failed to create initial plan",
                )

            self.current_plan = plan
            actions_taken.append(f"Created plan with {len(plan.steps)} steps")
            reasoning_steps.append(f"Created plan: {plan.goal}")

            logger.info(f"✅ Plan created successfully!")
            logger.info(f"   Goal: {plan.goal}")
            logger.info(f"   Steps ({len(plan.steps)}):")
            for i, step in enumerate(plan.steps):
                logger.info(f"     {i+1}. {step}")
            logger.info("\n")

            replan_count = 0

            # Phase 2: Execution Loop
            logger.info("\n🚀 PHASE 2: EXECUTION")
            logger.info("-" * 40)

            while not plan.is_complete() and replan_count <= self.max_replans:
                next_step_idx = plan.get_next_step()

                if next_step_idx is None:
                    break

                step = plan.steps[next_step_idx]
                logger.info(
                    f"\n▶️  Executing Step {next_step_idx + 1}/{len(plan.steps)}: {step}"
                )
                reasoning_steps.append(f"Executing step {next_step_idx + 1}: {step}")

                # Execute the step
                step_result = await self._execute_step(step, self.step_results)

                if step_result["success"]:
                    plan.completed_steps[next_step_idx] = True
                    self.step_results[f"step_{next_step_idx}"] = step_result["result"]
                    actions_taken.append(f"Completed: {step}")
                    reasoning_steps.append(
                        f"Step {next_step_idx + 1} completed successfully"
                    )
                    logger.info(f"✅ Step {next_step_idx + 1} completed successfully!")
                    logger.info(
                        f"   Result: {step_result['result'][:200]}..."
                        if len(str(step_result["result"])) > 200
                        else f"   Result: {step_result['result']}"
                    )
                else:
                    # Step failed - consider replanning
                    error_msg = step_result.get("error", "Unknown error")
                    reasoning_steps.append(
                        f"Step {next_step_idx + 1} failed: {error_msg}"
                    )
                    logger.warning(f"❌ Step {next_step_idx + 1} failed: {error_msg}")

                    if replan_count < self.max_replans:
                        logger.info(
                            f"\n🔄 REPLANNING (Attempt {replan_count + 1}/{self.max_replans})"
                        )
                        reasoning_steps.append("Attempting to replan")
                        new_plan = await self._replan(
                            plan, next_step_idx, step_result.get("error", "")
                        )

                        if new_plan:
                            plan = new_plan
                            self.current_plan = plan
                            replan_count += 1
                            actions_taken.append(f"Replanned (attempt {replan_count})")
                            reasoning_steps.append("Successfully replanned")
                        else:
                            return AgentResponse(
                                success=False,
                                result=None,
                                reasoning=" -> ".join(reasoning_steps),
                                actions_taken=actions_taken,
                                error=f"Failed to replan after step failure: {step}",
                            )
                    else:
                        return AgentResponse(
                            success=False,
                            result=None,
                            reasoning=" -> ".join(reasoning_steps),
                            actions_taken=actions_taken,
                            error=f"Max replanning attempts reached. Failed at: {step}",
                        )

            # Phase 3: Result
            if plan.is_complete():
                logger.info("\n✨ PHASE 3: SYNTHESIS")
                logger.info("-" * 40)
                reasoning_steps.append("All steps completed, synthesizing final result")
                final_result = await self._synthesize_results(task, self.step_results)

                logger.info(f"\n✅ TASK COMPLETED SUCCESSFULLY!")
                logger.info(
                    f"   Final result: {final_result[:200]}..."
                    if len(final_result) > 200
                    else f"   Final result: {final_result}"
                )
                logger.info("\n" + "=" * 80 + "\n")

                return AgentResponse(
                    success=True,
                    result=final_result,
                    reasoning=" -> ".join(reasoning_steps),
                    actions_taken=actions_taken,
                )
            else:
                return AgentResponse(
                    success=False,
                    result=None,
                    reasoning=" -> ".join(reasoning_steps),
                    actions_taken=actions_taken,
                    error="Plan execution incomplete",
                )

        except Exception as e:
            return AgentResponse(
                success=False,
                result=None,
                reasoning=" -> ".join(reasoning_steps),
                actions_taken=actions_taken,
                error=f"Unexpected error: {str(e)}",
            )

    async def _create_plan(self, task: str) -> Optional[Plan]:
        """Create an initial plan for the task."""
        logger.info("Creating plan...")
        planning_prompt = f"""You are a strategic planner. Create a step-by-step plan to accomplish this task:

Task: {task}

Create a clear, actionable plan with specific steps. Each step should be a concrete action that can be executed independently.

Respond in JSON format:
{{
    "goal": "The overall goal",
    "steps": ["Step 1 description", "Step 2 description", ...]
}}"""

        try:
            messages = [{"role": "user", "content": planning_prompt}]
            response = await self.llm.call(messages)

            # Parse the plan
            plan_data = json.loads(response.choices[0].message.content)
            return Plan(
                goal=plan_data["goal"],
                steps=plan_data["steps"],
                completed_steps=[False] * len(plan_data["steps"]),
            )
        except Exception as e:
            logger.error(f"Planning error: {e}")
            return None

    async def _execute_step(
        self, step: str, previous_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single step of the plan."""
        logger.info("   Getting available tools...")
        # Get available tools from MCP
        try:
            tool_schemas = await self.mcp_client.get_tools_definitions()
            logger.info(f"   Found {len(tool_schemas)} tools available")
        except Exception as e:
            logger.error(f"   Failed to get tools: {str(e)}")
            return {"success": False, "error": f"Failed to get tools: {str(e)}"}

        # Build context from previous results
        context = "Previous step results:\n"
        for key, value in previous_results.items():
            context += f"{key}: {value}\n"

        execution_prompt = f"""{context}

Current step to execute: {step}

Use the available tools to complete this step. Provide the result when done."""

        messages = [
            {
                "role": "system",
                "content": "You are an execution agent. Use tools to complete the given step.",
            },
            {"role": "user", "content": execution_prompt},
        ]

        # Execute with tool use (similar to ReAct pattern)
        for attempt in range(self.max_step_attempts):
            try:
                response = await self.llm.call(messages=messages, tools=tool_schemas)

                message = response.choices[0].message
                if message.tool_calls:
                    # Add the message directly - it's already in the correct format
                    messages.append(message.model_dump())

                    # Then execute each tool and add tool responses
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)

                        logger.info(f"   🔧 Using tool: {tool_name}({tool_args})")
                        result = await self.mcp_client.call_tool(tool_name, tool_args)
                        logger.info(
                            f"   📤 Tool result: {str(result)[:100]}..."
                            if len(str(result)) > 100
                            else f"   📤 Tool result: {result}"
                        )

                        # Add tool response with proper format
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result),
                        }
                        messages.append(tool_msg)
                else:
                    # No more tool calls, we have the result
                    return {"success": True, "result": message.content or ""}

            except Exception as e:
                if attempt == self.max_step_attempts - 1:
                    return {"success": False, "error": str(e)}

        return {"success": False, "error": "Max attempts reached"}

    async def _replan(
        self, current_plan: Plan, failed_step_idx: int, error: str
    ) -> Optional[Plan]:
        """Create a new plan based on current progress and failure."""
        logger.info("   Creating new plan to address the failure...")
        completed_info = "Completed steps:\n"
        for i, (step, completed) in enumerate(
            zip(current_plan.steps, current_plan.completed_steps)
        ):
            if completed:
                completed_info += f"✓ Step {i+1}: {step}\n"

        replan_prompt = f"""The original goal was: {current_plan.goal}

{completed_info}

Failed at step {failed_step_idx + 1}: {current_plan.steps[failed_step_idx]}
Error: {error}

Create a new plan that:
1. Builds on what has been completed
2. Addresses the failure
3. Achieves the original goal

Respond in JSON format:
{{
    "goal": "The overall goal",
    "steps": ["Step 1 description", "Step 2 description", ...]
}}"""

        try:
            messages = [{"role": "user", "content": replan_prompt}]
            response = await self.llm.call(messages)

            plan_data = json.loads(response.choices[0].message.content)
            new_plan = Plan(
                goal=plan_data["goal"],
                steps=plan_data["steps"],
                completed_steps=[False] * len(plan_data["steps"]),
            )

            logger.info("   ✅ New plan created:")
            logger.info(f"      Goal: {new_plan.goal}")
            logger.info(f"      Steps ({len(new_plan.steps)}):")
            for i, step in enumerate(new_plan.steps):
                logger.info(f"        {i+1}. {step}")

            return new_plan
        except Exception as e:
            logger.error(f"   Failed to create new plan: {e}")
            return None

    async def _synthesize_results(
        self, original_task: str, step_results: Dict[str, Any]
    ) -> str:
        """Synthesize all step results into a final answer."""
        logger.info("Synthesizing results from all steps...")
        logger.info(f"   Step results collected: {len(step_results)}")

        synthesis_prompt = f"""Original task: {original_task}

Results from executed steps:
{json.dumps(step_results, indent=2)}

Synthesize these results into a comprehensive answer to the original task. Be clear and concise."""

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
