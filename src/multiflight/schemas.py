"""Pydantic schemas shared by the public API and the Dify tools."""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class GroundDirectionParameters(BaseModel):
    """Bounded right-turn experiment settings, shared with the MATLAB worker."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    initial_speed_kn: float = Field(default=0, ge=0, le=5)
    target_nose_wheel_deg: float = Field(default=75, ge=20, le=75)
    target_heading_change_deg: float = Field(default=177, ge=150, le=180)
    max_simulation_time_s: float = Field(default=20, ge=5, le=20)


class GroundCorrectionParameters(BaseModel):
    """Test point 2-4: 100kn, trigger beyond 50ft, recover within 30ft."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    experiment: Literal["brake_correction"] = "brake_correction"
    initial_speed_kn: float = Field(default=100, ge=100, le=100)
    initial_lateral_deviation_ft: float = Field(default=45, ge=-80, le=80)
    initial_heading_deg: float = Field(default=2, ge=-5, le=5)
    max_simulation_time_s: float = Field(default=20, ge=5, le=20)


class RunRequest(BaseModel):
    scene_id: str = "engine_failure"
    preparation_id: Optional[str] = None
    prompt_version: Optional[str] = None
    query: Optional[str] = None
    parameters: Optional[Union[GroundDirectionParameters, GroundCorrectionParameters]] = None

    @model_validator(mode="after")
    def validate_scene_parameters(self):
        if self.parameters is not None and self.scene_id != "ground_direction":
            raise ValueError("parameters仅用于场景三；场景一参数请通过prepare接口提交")
        if self.scene_id == "ground_direction" and self.preparation_id:
            raise ValueError("场景三直接初始化，不使用场景一preparation_id")
        return self


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

