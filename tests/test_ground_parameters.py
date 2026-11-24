import json
import threading
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from multiflight.db import JobStore
from multiflight.evaluation import RunEvaluator
from multiflight.parameter_registry import ParameterRegistry
from multiflight.prompts import PromptCompiler, PromptStore
from multiflight.scene_registry import SceneRegistry
from multiflight.schemas import GroundDirectionParameters, RunRequest
from multiflight.services.run_service import RunService
from multiflight.simulation.ground_realtime import GroundRealtimeEnv


CUSTOM = dict(initial_speed_kn=5, target_nose_wheel_deg=40,
              target_heading_change_deg=150, max_simulation_time_s=12.25)


@pytest.mark.parametrize("invalid", [dict(initial_speed_kn=-1), dict(initial_speed_kn=6),
    dict(target_nose_wheel_deg=19), dict(target_nose_wheel_deg=76),
    dict(target_heading_change_deg=149), dict(max_simulation_time_s=21),
    dict(initial_speed_kn=float("nan")), dict(initial_speed_kn=float("inf")),
    dict(wind_speed_kn=1)])
def test_ground_parameters_reject_invalid_and_unknown_fields(invalid):
    with pytest.raises(ValidationError):
        GroundDirectionParameters(**invalid)


def test_api_accepts_ground_inputs_and_rejects_scene_mismatch(monkeypatch):
    import multiflight.main as api
    captured = []
    monkeypatch.setattr(api.run_service, "start", lambda *a, **kw: captured.append((a, kw)) or {"id": "test"})
    with TestClient(api.app) as client:
        examples = client.get("/openapi.json").json()["paths"]["/api/runs"]["post"]["requestBody"]["content"]["application/json"]["examples"]
        assert "ground_direction" in examples and "ground_brake" in examples
        schema = client.get("/api/scenarios/ground_direction/parameters").json()
        assert schema["requires_preparation"] is False
        fields = {f["name"] for g in schema["groups"] for f in g["fields"]}
        assert fields == set(CUSTOM)
        assert client.post("/api/runs", json={"scene_id": "ground_direction", "parameters": CUSTOM}).status_code == 202
        assert captured[-1][1]["parameters"] == CUSTOM
        assert client.post("/api/runs", json={"scene_id": "engine_failure", "parameters": CUSTOM}).status_code == 422
        assert client.post("/api/runs", json={"scene_id": "ground_direction", "parameters": {"initial_speed_kn": 6}}).status_code == 422
        assert client.post("/api/runs", json={"scene_id": "ground_direction", "preparation_id": "prep-old"}).status_code == 422
        assert client.post("/api/runs", json={"scene_id": "ground_deceleration"}).status_code == 409


@pytest.mark.parametrize("version", ["0.2.0", "0.3.0"])
def test_prompt_targets_match_runtime_configuration(version):
    scene = SceneRegistry().get("ground_direction")
    compiler = PromptCompiler()
    prompt = compiler.compile(scene, version, runtime_context={"normalized_parameters": CUSTOM})
    assert "{{" not in prompt.text
    assert "初始地速5kn" in prompt.text
    assert "航向变化150度" in prompt.text and "12.25秒" in prompt.text
    assert "ground_runtime_parameters" in prompt.block_hashes
    assert prompt.protected_hash != compiler.compile(scene, version).protected_hash


def test_reset_hands_same_configuration_to_worker_and_allows_initial_5kn(tmp_path, monkeypatch):
    monkeypatch.setattr("multiflight.simulation.ground_realtime.RUN_DIR", tmp_path)
    worker = SimpleNamespace(wait=lambda **kw: None)
    monkeypatch.setattr("multiflight.simulation.ground_realtime.subprocess.Popen", lambda *a, **kw: worker)
    env = GroundRealtimeEnv("reset", {"normalized_parameters": CUSTOM})
    waits = []
    monkeypatch.setattr(env, "_wait", lambda *a, **kw: waits.append((a, kw)) or {"ready": True})
    try:
        state = env.reset()["state"]
        assert state["speed_kn"] == 5 and state["reached_5kn"]
        assert waits[0][1]["timeout"] == 180
        assert json.loads((env.folder / "configuration.json").read_text()) == CUSTOM
        with pytest.raises(ValueError, match="目标转角"):
            env.step(dict(nose_wheel_deg=41, throttle_left=0, throttle_right=0))
        assert not (env.folder / "request_001.json").exists()
    finally:
        env.close()


def test_fractional_time_limit_is_terminal_instead_of_an_extra_step(tmp_path, monkeypatch):
    monkeypatch.setattr("multiflight.simulation.ground_realtime.RUN_DIR", tmp_path)
    env = GroundRealtimeEnv("deadline", {"normalized_parameters": {**CUSTOM, "max_simulation_time_s": 5.25}})
    env.state = {"flight_phase": "TURN"}
    env.sequence = 10
    env.reached_5 = True
    response = dict(time_s=5.25, speed_kn=3, heading_deg=90, yaw_rate_deg_s=1,
                    wheel_deg=40, x_m=1, y_m=1, roll_deg=0, on_ground=True, safe=True, complete=False)
    monkeypatch.setattr(env, "_wait", lambda *a, **kw: response)
    result = env.step(dict(nose_wheel_deg=40, throttle_left=0, throttle_right=0))
    assert result["done"] and result["state"]["flight_phase"] == "FAILED"
    with pytest.raises(ValueError, match="finished"):
        env.step(dict(nose_wheel_deg=40, throttle_left=0, throttle_right=0))


class ImmediateExecutor:
    def submit(self, fn, *args):
        return fn(*args)


class ScenarioSimulator:
    def begin_run(self, run_id, scene_id, callback, configuration):
        self.configuration = configuration
        self.records = []

    def reset(self):
        self.state = {"flight_phase": "READY", "reached_5kn": True, "speed_kn": 5, "time": 0}
        result = {"state": self.state, "done": False}
        self.records.append({"kind": "reset", "result": result})
        return result

    def step(self, action):
        index = len(self.records)
        state = {"flight_phase": "SUCCESS" if index == 3 else "TURN", "time": index * .5,
                 "speed_kn": 5, "reached_5kn": True, "heading_deg": index * 50}
        sim = dict(start_time_s=(index-1)*.5, time_s=index*.5, initial_x_m=0, initial_y_m=0,
                   x_m=0, y_m=0, initial_speed_kn=5, speed_kn=5, safe=True, on_ground=True,
                   max_wheel_deg=40, heading_deg=index*50, complete=index == 3)
        if self.configuration["brake_protocol"]:
            sim.update(brake_left=0, brake_right=0, brake_system_mode=0,
                       auto_brake_active=False, auto_brake_min_level=.15, max_steering_excess_deg=0)
        result = {"state": state, "done": index == 3, "simulation": sim}
        self.records.append({"kind": "step", "raw_action": action, "state_before": self.state, "result": result})
        self.state = state
        return result

    def snapshot(self):
        return self.records

    def finish_run(self):
        self.closed = True


@pytest.mark.parametrize("version", ["0.2.0", "0.3.0"])
def test_custom_run_passes_parameters_to_prompt_simulation_evaluation_and_archive(tmp_path, monkeypatch, version):
    monkeypatch.setattr("multiflight.services.run_service.RUN_DIR", tmp_path)
    calls = []
    def decide(**kw):
        calls.append(kw)
        return {"answer": json.dumps(dict(nose_wheel_deg=40, throttle_left=.1, throttle_right=0))}
    simulator = ScenarioSimulator()
    service = RunService(jobs=JobStore(tmp_path / "jobs.db"), scenes=SceneRegistry(),
        prompts=PromptStore(tmp_path / "prompts.json"), compiler=PromptCompiler(),
        simulator=simulator, dify=SimpleNamespace(run_agent=decide), evaluator=RunEvaluator(),
        executor=ImmediateExecutor(), execution_lock=threading.Lock())
    queued = service.start("ground_direction", version, parameters=CUSTOM)
    job = service.jobs.get(queued["id"])
    assert job["status"] == "succeeded"
    assert job["payload"]["parameters"] == simulator.configuration["normalized_parameters"] == CUSTOM
    assert job["result"]["parameters"] == job["result"]["evaluation"]["parameters"] == CUSTOM
    assert len(calls) == job["result"]["dify"]["model_calls"] == 3
    assert job["result"]["dify"]["reused_decisions"] == 0
    assert "航向变化150度" in calls[0]["scene_prompt"]
    assert "target_angle_reached" in job["result"]["evaluation"]["hard_gates"]
    assert simulator.closed
    records = simulator.snapshot()
    context = {"normalized_parameters": CUSTOM}
    bad = deepcopy(records)
    bad[1]["result"]["simulation"]["initial_speed_kn"] = 0
    assert not RunEvaluator().evaluate(SceneRegistry().get("ground_direction"), bad, version, "test", context)["hard_gates"]["state_continuity"]
    bad = deepcopy(records)
    bad[-1]["result"]["simulation"]["heading_deg"] = 149
    assert not RunEvaluator().evaluate(SceneRegistry().get("ground_direction"), bad, "0.2.0", "test", context)["passed"]
    bad = deepcopy(records)
    for r in bad[1:]:
        r["result"]["simulation"]["max_wheel_deg"] = 39
    assert not RunEvaluator().evaluate(SceneRegistry().get("ground_direction"), bad, "0.2.0", "test", context)["passed"]
    with pytest.raises(ValueError, match="0.2/0.3"):
        service.start("ground_direction", "0.1.0", parameters=CUSTOM)


def test_omitted_parameters_keep_existing_defaults():
    assert RunRequest(scene_id="ground_direction").parameters is None
    assert ParameterRegistry().defaults("ground_direction") == dict(
        initial_speed_kn=0, target_nose_wheel_deg=75, target_heading_change_deg=177, max_simulation_time_s=20)
