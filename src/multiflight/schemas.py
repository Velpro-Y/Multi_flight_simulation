"""Pydantic schemas shared by the public API and the Dify tools."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
    preparation_id: Optional[str] = None
    prompt_version: Optional[str] = None
    query: Optional[str] = None


class EngineFailureParameters(BaseModel):
    """Validated user inputs for the parameterized engine-failure scene."""

    initial_altitude_ft: float = Field(default=500.0, ge=400.0, le=1000.0)
    initial_airspeed_ft_s: float = Field(
        default=148.911745406824, ge=135.0, le=165.0
    )
    engine_failure_altitude_ft: float = Field(default=300.0, ge=250.0, le=800.0)
    go_around_altitude_ft: float = Field(default=200.0, ge=100.0, le=700.0)
    target_altitude_ft: float = Field(default=500.0, ge=400.0, le=1500.0)
    wind_speed_ft_s: float = Field(default=0.0, ge=0.0, le=30.0)
    wind_direction_deg: float = Field(default=0.0, ge=0.0, le=360.0)
    max_simulation_time_s: float = Field(default=300.0, ge=60.0, le=600.0)

    @model_validator(mode="after")
    def validate_altitude_order(self) -> "EngineFailureParameters":
        if self.initial_altitude_ft <= self.engine_failure_altitude_ft:
            raise ValueError("初始高度必须高于左发失效高度")
        if self.engine_failure_altitude_ft <= self.go_around_altitude_ft:
            raise ValueError("左发失效高度必须高于复飞高度")
        if self.target_altitude_ft <= self.go_around_altitude_ft:
            raise ValueError("目标高度必须高于复飞高度")
        return self


class PreparationRequest(BaseModel):
    scene_id: str = "engine_failure"
    parameters: EngineFailureParameters = Field(
        default_factory=EngineFailureParameters
    )


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

