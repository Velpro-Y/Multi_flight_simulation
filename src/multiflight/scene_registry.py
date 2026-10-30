"""Load and validate versioned scene definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from .settings import SCENE_DIR


class InitializationSpec(BaseModel):
    altitude_ft: Optional[float] = None
    trim_profile: str


class PhaseSpec(BaseModel):
    id: str
    description: str
    transition: Optional[str] = None
    success: Optional[str] = None


class SafetySpec(BaseModel):
    min_airspeed_ft_s: Optional[float] = None
    max_airspeed_ft_s: Optional[float] = None
    max_abs_roll_rad: Optional[float] = None
    min_pitch_rad: Optional[float] = None
    max_pitch_rad: Optional[float] = None
    max_steps: int = Field(default=150, ge=1)


class SceneSpec(BaseModel):
    scene_id: str
    name: str
    version: str
    status: Literal["enabled", "reserved", "planned"]
    description: str
    unavailable_reason: Optional[str] = None
    initialization: InitializationSpec
    phases: list[PhaseSpec]
    observation_fields: list[str]
    action_fields: list[str]
    protected_prompt_blocks: list[str]
    optimizable_prompt_blocks: list[str]
    safety: SafetySpec
    expected_phase_order: list[str]


class SceneRegistry:
    def __init__(self, scene_dir: Path = SCENE_DIR):
        self.scene_dir = scene_dir
        self._scenes: dict[str, SceneSpec] = {}
        self.reload()

    def reload(self) -> None:
        scenes: dict[str, SceneSpec] = {}
        for path in sorted(self.scene_dir.glob("*.yaml")):
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
            spec = SceneSpec.model_validate(raw)
            if spec.scene_id in scenes:
                raise ValueError(f"Duplicate scene_id: {spec.scene_id}")
            scenes[spec.scene_id] = spec
        self._scenes = scenes

    def list(self) -> list[SceneSpec]:
        return list(self._scenes.values())

    def get(self, scene_id: str) -> SceneSpec:
        try:
            return self._scenes[scene_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scene_id: {scene_id}") from exc

