"""Pydantic schemas shared by the public API and the Dify tools."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Action(BaseModel):
    """One control action produced by the decision model."""

    aileron: Any = Field(default=0.0)
    elevator: Any = Field(default=0.0)
    rudder: Any = Field(default=0.0)
    throttle_left: Any = Field(default=0.5)
    throttle_right: Any = Field(default=0.5)
    left_engine_fail: bool = False

    @field_validator(
        "aileron",
        "elevator",
        "rudder",
        "throttle_left",
        "throttle_right",
        mode="before",
    )
    @classmethod
    def clean_float(cls, value: Any) -> float:
        if isinstance(value, str):
            value = value.replace('"', "").replace("'", "").strip()
            value = value.replace("- ", "-")
        return float(value)


class RunRequest(BaseModel):
    scene_id: str = "engine_failure"
    prompt_version: Optional[str] = None
    query: Optional[str] = None


class OptimizationRequest(BaseModel):
    scene_id: str = "engine_failure"
    candidate_count: int = Field(default=2, ge=1, le=2)
    auto_publish: bool = False


class PublishRequest(BaseModel):
    reason: str = "manual approval"


class SessionRequest(BaseModel):
    scene_id: str = "engine_failure"


class JobSummary(BaseModel):
    id: str
    kind: Literal["run", "optimization"]
    status: str
    progress: float
    message: str
    result: Optional[dict[str, Any]] = None

