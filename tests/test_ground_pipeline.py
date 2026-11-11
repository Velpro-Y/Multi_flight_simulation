from copy import deepcopy

from multiflight.evaluation.evaluator import RunEvaluator
from multiflight.prompts import PromptCompiler, PromptStore
from multiflight.scene_registry import SceneRegistry
from multiflight.prompts.candidates import CandidateGenerator


def test_ground_prompt_seed_and_protection(tmp_path):
    store = PromptStore(tmp_path / "registry.json")
    assert store.get("ground_direction")["version"] == "0.2.0"
    scene = SceneRegistry().get("ground_direction")
    a = PromptCompiler().compile(scene, "0.1.0")
    b = PromptCompiler().compile(scene, "0.1.1", "先检查当前阶段")
    assert a.protected_hash == b.protected_hash
    assert "TURN_READY" in a.text and "75" in a.text
    assert "左发失效后" not in a.text


def test_ground_evaluator_rejects_replayed_state():
    action = dict(aileron=0, elevator=0, rudder=0, throttle_left=0.4, throttle_right=0.4)
    first = dict(duration_s=3.85, final_x_m=5, final_y_m=0, final_speed_kn=5.05, safe=True, all_wheels_contact=True)
    final = dict(start_time_s=3.85, initial_x_m=5, initial_y_m=0, initial_speed_kn=5.05,
                 safe=True, all_wheels_contact=True, max_actual_front_wheel_angle_deg=75,
                 passed=True, reverse_motion=True)
    records = [{"kind": "reset", "result": {"state": {"flight_phase": "READY"}}}]
    for phase, sim in [("TURN_READY", first), ("SUCCESS", final)]:
        records.append({"kind": "step", "raw_action": action,
                        "result": {"state": {"flight_phase": phase}, "simulation": sim, "done": phase == "SUCCESS"}})
    scene = SceneRegistry().get("ground_direction")
    evaluator = RunEvaluator()
    assert evaluator.evaluate(scene, records, "0.1.0", "hash")["passed"]
    replay = deepcopy(records); replay[-1]["result"]["simulation"]["initial_x_m"] = 0
    assert "STATE_DISCONTINUITY" in evaluator.evaluate(scene, replay, "0.1.0", "hash")["failure_labels"]
    sampled = deepcopy(records)
    sampled[-1]["result"]["simulation"].update(start_time_s=3.85001, initial_x_m=5.000026, initial_speed_kn=5.050012)
    assert evaluator.evaluate(scene, sampled, "0.1.0", "hash")["passed"]
    sampled[-1]["result"]["simulation"]["start_time_s"] = 3.9
    assert not evaluator.evaluate(scene, sampled, "0.1.0", "hash")["passed"]


def test_ground_candidates_do_not_use_airborne_policy():
    candidates = CandidateGenerator().generate(2, scene_id="ground_direction")
    assert len(candidates) == 2
    assert all("GO_AROUND" not in c.addendum for c in candidates)
    assert "TURN_READY" in candidates[0].addendum


def test_realtime_contract_and_action_are_direct_controls():
    import pytest
    from pydantic import ValidationError
    from multiflight.simulation.ground_realtime import GroundRealtimeAction
    scene = SceneRegistry().get("ground_direction")
    prompt = PromptCompiler().compile(scene, "0.2.0")
    assert "不使用PI" in prompt.text
    assert "只输出一个JSON" in prompt.text
    assert "首先调用" not in prompt.text
    assert GroundRealtimeAction(nose_wheel_deg=75, throttle_left=.4, throttle_right=0).nose_wheel_deg == 75
    with pytest.raises(ValidationError):
        GroundRealtimeAction(nose_wheel_deg=90, throttle_left=.4, throttle_right=0)
