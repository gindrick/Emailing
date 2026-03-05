from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class AgentResponse:
    """Response from an agent execution."""

    success: bool
    result: Any
    reasoning: str
    actions_taken: List[str]
    error: Optional[str] = None


class Agent(ABC):
    """Base abstract class for all agents."""

    def __init__(self, name: str):
        self.name = name
        self.conversation_history: List[Dict[str, Any]] = []

    @abstractmethod
    async def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """Execute a task and return the response."""
        pass

    def add_to_history(self, message: Dict[str, Any]):
        """Add message to conversation history.

        Args:
            message: A message dict that can contain any fields required by the LLM API
                    (e.g., role, content, tool_calls, tool_call_id, etc.)
        """
        self.conversation_history.append(message)

    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history."""
        return self.conversation_history

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
