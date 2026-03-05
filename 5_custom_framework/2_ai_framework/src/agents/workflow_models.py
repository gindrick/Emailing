"""Pydantic models for structured outputs in workflow execution"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class WorkflowTaskOutput(BaseModel):
    """Output model for task nodes in workflow"""
    
    result: str = Field(
        description="The main result or output of the task execution"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Variables to store in workflow state for use by subsequent nodes"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "result": "Successfully analyzed the data and found 3 key insights",
                    "variables": {
                        "insights_count": 3,
                        "analysis_summary": "Data shows positive trend...",
                        "key_metrics": {"growth": 0.15, "retention": 0.85}
                    }
                }
            ]
        }


class WorkflowConditionOutput(BaseModel):
    """Output model for condition nodes in workflow"""
    
    condition_met: bool = Field(
        description="Whether the condition was met (true) or not (false)"
    )
    reasoning: str = Field(
        description="Explanation of why the condition was or wasn't met"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional variables to store based on condition evaluation"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "condition_met": True,
                    "reasoning": "The search results contain relevant information about AI trends",
                    "variables": {
                        "has_relevant_results": True,
                        "result_quality": "high"
                    }
                }
            ]
        }