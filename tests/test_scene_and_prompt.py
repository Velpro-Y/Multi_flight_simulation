from __future__ import annotations

from multiflight.prompts import PromptCompiler
from multiflight.prompts.candidates import CandidateGenerator
from multiflight.scene_registry import SceneRegistry


def test_scene_registry_exposes_expected_statuses() -> None:
    registry = SceneRegistry()
    statuses = {scene.scene_id: scene.status for scene in registry.list()}
    assert statuses == {
        "engine_failure": "enabled",
        "ground_deceleration": "reserved",
        "ground_direction": "enabled",
    }


def test_prompt_candidate_cannot_change_protected_hash() -> None:
    scene = SceneRegistry().get("engine_failure")
    compiler = PromptCompiler()
    baseline = compiler.compile(scene, "1.0.0")
    candidate = compiler.compile(scene, "1.0.1", "只修改允许优化的决策检查表。")
    assert baseline.protected_hash == candidate.protected_hash
    assert baseline.prompt_hash != candidate.prompt_hash
    assert "ENGINE_OUT_DESCENT" in baseline.text


def test_control_failure_prioritizes_sign_guard_candidate() -> None:
    candidates = CandidateGenerator().generate(1, ["CONTROL_SIGN_ERROR"])
    assert candidates[0].name == "control_sign_guard"
    assert "yaw_rate > 0.03" in candidates[0].addendum

