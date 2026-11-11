"""Deterministically assemble protected and optimizable prompt blocks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..scene_registry import SceneSpec
from ..settings import PROMPT_DIR
from ..schemas import EngineFailureParameters
from ..settings import (
    ENGINE_OUT_CLIMB_TRIM,
    ENGINE_OUT_DESCENT_TRIM,
    TWIN_DESCENT_TRIM,
)


@dataclass(frozen=True)
class PromptArtifact:
    scene_id: str
    version: str
    text: str
    prompt_hash: str
    protected_hash: str
    block_hashes: dict[str, str]


class PromptCompiler:
    PROTECTED_FILES = {
        "base_role": "base_role.md",
        "model_facts": "model_facts.md",
        "tool_contract": "tool_contract.md",
        "ground_contract": "ground_contract.md",
    }

    def __init__(self, prompt_dir: Path = PROMPT_DIR):
        self.prompt_dir = prompt_dir

    def compile(
        self,
        scene: SceneSpec,
        version: str,
        addendum: str = "",
        runtime_context: Optional[dict[str, Any]] = None,
    ) -> PromptArtifact:
        if scene.status != "enabled":
            raise ValueError(f"Scene {scene.scene_id} is not enabled")

        protected: list[tuple[str, str]] = []
        for block_name in scene.protected_prompt_blocks:
            filename = self.PROTECTED_FILES[block_name]
            protected.append((block_name, self._read(filename)))

        scene_text = self._read(f"scenes/{scene.scene_id}.md")
        if scene.scene_id == "ground_direction" and version.startswith("0.2."):
            protected = [("ground_realtime_contract", self._read("ground_realtime_contract.md"))]
            scene_text = self._read("scenes/ground_direction_realtime.md")
        if scene.scene_id == "engine_failure":
            context = _engine_failure_context(runtime_context)
            protected.append(
                ("runtime_parameters", _runtime_parameter_block(context))
            )
            scene_text = _render_engine_failure_scene(scene_text, context)
        blocks = protected + [("scene_policy", scene_text)]
        if addendum.strip():
            blocks.append(("decision_checklist", addendum.strip()))

        block_hashes = {name: _sha256(text) for name, text in blocks}
        protected_text = "\n\n".join(text for _, text in protected)
        compiled = "\n\n---\n\n".join(text.strip() for _, text in blocks).strip() + "\n"
        return PromptArtifact(
            scene_id=scene.scene_id,
            version=version,
            text=compiled,
            prompt_hash=_sha256(compiled),
            protected_hash=_sha256(protected_text),
            block_hashes=block_hashes,
        )

    def _read(self, relative_path: str) -> str:
        path = self.prompt_dir / relative_path
        return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _engine_failure_context(
    preparation: Optional[dict[str, Any]],
) -> dict[str, Any]:
    parameters = EngineFailureParameters().model_dump()
    profiles: dict[str, Any] = {
        "twin_descent": TWIN_DESCENT_TRIM,
        "engine_out_descent": ENGINE_OUT_DESCENT_TRIM,
        "engine_out_climb": ENGINE_OUT_CLIMB_TRIM,
    }
    if preparation:
        parameters.update(preparation.get("normalized_parameters", {}))
        profiles.update(preparation.get("trim", {}).get("profiles", {}))
    return {"parameters": parameters, "profiles": profiles}


def _render_engine_failure_scene(
    text: str, context: dict[str, Any]
) -> str:
    parameters = context["parameters"]
    replacements = {
        "{{initial_altitude_ft}}": parameters["initial_altitude_ft"],
        "{{engine_failure_altitude_ft}}": parameters[
            "engine_failure_altitude_ft"
        ],
        "{{go_around_altitude_ft}}": parameters["go_around_altitude_ft"],
        "{{target_altitude_ft}}": parameters["target_altitude_ft"],
    }
    for marker, value in replacements.items():
        text = text.replace(marker, f"{float(value):.1f}")
    return text


def _runtime_parameter_block(context: dict[str, Any]) -> str:
    parameters = context["parameters"]
    profiles = context["profiles"]
    lines = [
        "# 本次实验参数与配平",
        "",
        "以下数值由后端校验和配平生成，本次实验以此处数值为准：",
        "",
        f"- 初始高度：{parameters['initial_altitude_ft']:.1f} ft",
        f"- 初始空速：{parameters['initial_airspeed_ft_s']:.3f} ft/s",
        f"- 左发失效高度：{parameters['engine_failure_altitude_ft']:.1f} ft",
        f"- 复飞高度：{parameters['go_around_altitude_ft']:.1f} ft",
        f"- 目标高度：{parameters['target_altitude_ft']:.1f} ft",
        f"- 最长仿真时间：{parameters['max_simulation_time_s']:.1f} s",
    ]
    for label, name in (
        ("双发下降", "twin_descent"),
        ("单发下降", "engine_out_descent"),
        ("单发复飞", "engine_out_climb"),
    ):
        trim = profiles[name]
        lines.extend(
            [
                "",
                f"## {label}配平",
                f"- aileron={float(trim['aileron']):.6f}",
                f"- elevator={float(trim['elevator']):.6f}",
                f"- rudder={float(trim['rudder']):.6f}",
                f"- throttle_left={float(trim['throttle_left']):.6f}",
                f"- throttle_right={float(trim['throttle_right']):.6f}",
                f"- target_airspeed={float(trim['airspeed']):.3f} ft/s",
                f"- target_vertical_speed={float(trim['vertical_speed']):.3f} ft/s",
            ]
        )
    return "\n".join(lines)

