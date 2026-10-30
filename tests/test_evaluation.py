from __future__ import annotations

from multiflight.evaluation import RegressionGate, RunEvaluator
from multiflight.scene_registry import SceneRegistry


def _step(
    sequence: int,
    phase_before: str,
    phase_after: str,
    altitude: float,
    done: bool = False,
) -> dict:
    trims = {
        "TWIN_DESCENT": (0.00203, -0.01097, -0.03744, 0.16863, 0.16863),
        "ENGINE_OUT_DESCENT": (0.00082, -0.01096, -0.05206, 0.0, 0.20722),
        "GO_AROUND": (-0.01955, -0.00965, -0.29909, 0.0, 0.61470),
        "SUCCESS": (-0.01955, -0.00965, -0.29909, 0.0, 0.61470),
    }
    values = trims[phase_before]
    action = {
        "aileron": values[0],
        "elevator": values[1],
        "rudder": values[2],
        "throttle_left": values[3],
        "throttle_right": values[4],
    }
    return {
        "sequence": sequence,
        "kind": "step",
        "state_before": {
            "flight_phase": phase_before,
            "roll": 0.02,
            "yaw_rate": 0.0,
        },
        "raw_action": action,
        "applied_action": action,
        "result": {
            "done": done,
            "event": "GO_AROUND_SUCCESS" if done else "NORMAL",
            "state": {
                "flight_phase": phase_after,
                "altitude": altitude,
                "airspeed": 149.0,
                "roll": 0.02,
                "pitch": 0.08,
            },
        },
    }


def test_passing_run_and_regression_gate() -> None:
    scene = SceneRegistry().get("engine_failure")
    records = [
        _step(1, "TWIN_DESCENT", "TWIN_DESCENT", 350.0),
        _step(2, "TWIN_DESCENT", "ENGINE_OUT_DESCENT", 299.0),
        _step(3, "ENGINE_OUT_DESCENT", "GO_AROUND", 199.0),
        _step(4, "GO_AROUND", "SUCCESS", 500.0, done=True),
    ]
    evaluator = RunEvaluator()
    baseline = evaluator.evaluate(scene, records, "1.0.0", "hash-a")
    candidate = evaluator.evaluate(scene, records, "1.0.1", "hash-b")
    assert baseline["passed"] is True
    report = RegressionGate().compare(baseline, candidate, True)
    assert report["passed"] is True
    assert report["decision"] == "non_regression_only"


def test_early_go_around_is_rejected() -> None:
    scene = SceneRegistry().get("engine_failure")
    records = [
        _step(1, "TWIN_DESCENT", "TWIN_DESCENT", 350.0),
        _step(2, "TWIN_DESCENT", "GO_AROUND", 280.0),
    ]
    result = RunEvaluator().evaluate(scene, records, "bad", "bad-hash")
    assert result["passed"] is False
    assert "PHASE_EARLY" in result["failure_labels"]


def test_climbing_above_trigger_is_not_marked_as_early() -> None:
    scene = SceneRegistry().get("engine_failure")
    records = [
        _step(1, "TWIN_DESCENT", "ENGINE_OUT_DESCENT", 299.0),
        _step(2, "ENGINE_OUT_DESCENT", "GO_AROUND", 199.0),
        _step(3, "GO_AROUND", "GO_AROUND", 260.0),
        _step(4, "GO_AROUND", "SUCCESS", 500.0, done=True),
    ]
    result = RunEvaluator().evaluate(scene, records, "fixed", "fixed-hash")
    assert result["hard_gates"]["no_early_go_around"] is True
    assert "PHASE_EARLY" not in result["failure_labels"]

