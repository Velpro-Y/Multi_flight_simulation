"""Real MATLAB parameter/termination checks with fixed test inputs, zero Dify calls."""

import argparse
import json
import uuid

from multiflight.settings import RUN_DIR
from multiflight.simulation import SimulationManager
from multiflight.evaluation import RunEvaluator
from multiflight.scene_registry import SceneRegistry
from multiflight.schemas import GroundDirectionParameters


CASES = {
    "default": (False, {}, False),
    "custom": (False, dict(initial_speed_kn=5, target_nose_wheel_deg=40,
                           target_heading_change_deg=150, max_simulation_time_s=20), False),
    "brake_deadline": (True, dict(initial_speed_kn=2, target_nose_wheel_deg=40,
                                target_heading_change_deg=150, max_simulation_time_s=5.25), True),
}


def verify(name):
    brake, settings, expect_timeout = CASES[name]
    parameters = GroundDirectionParameters(**settings).model_dump()
    run_id = "ground-parameters-" + name + "-" + uuid.uuid4().hex[:8]
    folder = RUN_DIR / run_id
    folder.mkdir(parents=True)
    manager = SimulationManager()
    checks = {}
    error = None
    try:
        manager.begin_run(run_id, "ground_direction", configuration={"mode": "realtime",
                          "brake_protocol": brake, "normalized_parameters": parameters})
        result = manager.reset()
        checks["reset_speed"] = result["state"]["speed_kn"] == parameters["initial_speed_kn"]
        first = None
        for _ in range(40):
            turning = result["state"]["reached_5kn"]
            # Test-only fixed thrust settings, never presented as Dify decisions.
            throttle = .1 if turning else .4
            action = dict(nose_wheel_deg=parameters["target_nose_wheel_deg"] if turning else 0,
                          throttle_left=throttle, throttle_right=throttle)
            result = manager.step(action)
            sim = result["simulation"]
            if first is None:
                first = sim
            print(name, result["state"]["time"], round(sim["speed_kn"], 3),
                  round(sim["heading_deg"], 3), flush=True)
            if result["done"]:
                break
        steps = [r["result"]["simulation"] for r in manager.snapshot() if r["kind"] == "step"]
        checks["model_initial_speed"] = abs(first["initial_speed_kn"]-parameters["initial_speed_kn"]) < .001
        checks["safe_and_grounded"] = all(s["safe"] and s["on_ground"] for s in steps)
        checks["time_limit"] = sim["time_s"] <= parameters["max_simulation_time_s"] + 1e-6
        checks["wheel_bound"] = all(s["max_wheel_deg"] <= parameters["target_nose_wheel_deg"] + .1 for s in steps)
        checks["terminal"] = result["done"]
        if expect_timeout:
            checks["fractional_deadline"] = abs(sim["time_s"]-parameters["max_simulation_time_s"]) < 1e-6
            checks["failed_phase"] = result["state"]["flight_phase"] == "FAILED" and not sim["complete"]
        else:
            checks["completed_at_target"] = sim["complete"] and sim["heading_deg"] >= parameters["target_heading_change_deg"]
        evaluation = RunEvaluator().evaluate(SceneRegistry().get("ground_direction"), manager.snapshot(),
            "0.3.0" if brake else "0.2.0", "fixed-model-test", {"normalized_parameters": parameters})
        checks["evaluation_matches_outcome"] = evaluation["passed"] == (not expect_timeout)
        (folder / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        error = str(exc)
    finally:
        (folder / "records.json").write_text(json.dumps(manager.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        manager.finish_run()
    report = dict(run_id=run_id, case=name, parameters=parameters, checks=checks,
                  passed=bool(checks) and all(checks.values()) and error is None,
                  error=error, dify_calls=0, decision_source="fixed_model_test")
    (folder / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    args = parser.parse_args()
    reports = [verify(name) for name in CASES if args.case in {"all", name}]
    raise SystemExit(0 if all(r["passed"] for r in reports) else 1)
