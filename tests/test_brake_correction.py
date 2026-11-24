import json
import threading
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from multiflight.db import JobStore
from multiflight.evaluation import RunEvaluator
from multiflight.prompts import PromptCompiler, PromptStore
from multiflight.scene_registry import SceneRegistry
from multiflight.schemas import GroundCorrectionParameters, RunRequest
from multiflight.services.run_service import RunService
from multiflight.simulation.ground_realtime import GroundCorrectionAction, GroundRealtimeEnv


P=GroundCorrectionParameters().model_dump()


def test_preview_candidate_changes_policy_without_changing_constraints(tmp_path):
    store=PromptStore(tmp_path/"registry.json");candidate=store.get("ground_direction","0.4.1")
    assert candidate["status"]=="candidate" and store.get("ground_direction")["version"]=="0.2.0"
    compiler=PromptCompiler();scene=SceneRegistry().get("ground_direction");context={"normalized_parameters":P}
    old=compiler.compile(scene,"0.4.0",runtime_context=context)
    new=compiler.compile(scene,"0.4.1",candidate["addendum"],runtime_context=context)
    assert new.protected_hash==old.protected_hash and new.prompt_hash!=old.prompt_hash
    assert "e_pred" in new.text and "0.12" in new.text


@pytest.mark.parametrize("fields", [dict(initial_speed_kn=5),dict(initial_speed_kn=float("nan")),
    dict(initial_heading_deg=6),dict(initial_lateral_deviation_ft=81),dict(target_nose_wheel_deg=75)])
def test_correction_parameters_are_separate_from_turning(fields):
    with pytest.raises(ValidationError):GroundCorrectionParameters(**fields)


@pytest.mark.parametrize("fields", [dict(nose_wheel_deg=1),dict(throttle_left=.1,throttle_right=0),
    dict(brake_system_mode=1),dict(auto_brake_armed=True),dict(brake_left=1.1)])
def test_correction_action_excludes_other_direction_actuators(fields):
    with pytest.raises(ValidationError):
        GroundCorrectionAction.model_validate({"throttle_left":0,"throttle_right":0,**fields})


def test_correction_schema_prompt_and_candidate_do_not_replace_published_turn(tmp_path,monkeypatch):
    import multiflight.main as api
    captured=[]
    monkeypatch.setattr(api.run_service,"start",lambda *a,**kw:captured.append(kw) or {"id":"test"})
    with TestClient(api.app) as c:
        meta=c.get("/api/scenarios/ground_direction/parameters?experiment=brake_correction").json()
        assert meta["supported_prompt_versions"]==["0.4.0","0.4.1"]
        assert meta["parameter_defaults"]==P
        assert c.post("/api/runs",json={"scene_id":"ground_direction","prompt_version":"0.4.0","parameters":P}).status_code==202
        assert captured[-1]["parameters"]==P
        assert "0.4.0" in c.get("/api/ground-direction/action-schemas").json()
    assert isinstance(RunRequest(scene_id="ground_direction",parameters=P).parameters,GroundCorrectionParameters)
    store=PromptStore(tmp_path/"registry.json")
    assert store.get("ground_direction")["version"]=="0.2.0"
    assert store.get("ground_direction","0.4.0")["status"]=="candidate"
    prompt=PromptCompiler().compile(SceneRegistry().get("ground_direction"),"0.4.0",runtime_context={"normalized_parameters":P})
    assert "{{" not in prompt.text and "50ft" in prompt.text and "30ft" in prompt.text
    assert "target_heading_change_deg" not in prompt.text


def test_correction_env_rejects_braking_before_trigger(tmp_path,monkeypatch):
    monkeypatch.setattr("multiflight.simulation.ground_realtime.RUN_DIR",tmp_path)
    env=GroundRealtimeEnv("test",{"correction_protocol":True,"normalized_parameters":P})
    assert env.brake_protocol
    env.state={"flight_phase":"MONITOR"};env.reached_5=True
    with pytest.raises(ValueError,match="50ft"):
        env.step(dict(throttle_left=0,throttle_right=0,brake_left=.1))
    assert not (env.folder/"request_001.json").exists()


def fixture_records():
    records=[{"kind":"reset","result":{"state":{"flight_phase":"MONITOR","speed_kn":100}}}]
    previous_y=45*.3048
    for i,(deviation,stable,left,right) in enumerate([(51,0,0,0),(29,0,.4,0),(28,.5,0,.1),(28,1,0,0)],1):
        action=GroundCorrectionAction(throttle_left=0,throttle_right=0,brake_left=left,brake_right=right).model_dump()
        sim=dict(time_s=i*.5,start_time_s=(i-1)*.5,x_m=i*25,y_m=deviation*.3048,
            initial_x_m=(i-1)*25,initial_y_m=previous_y,initial_speed_kn=100,speed_kn=100,
            safe=True,on_ground=True,max_wheel_deg=0,heading_deg=0,yaw_rate_deg_s=0,
            lateral_velocity_m_s=0,lateral_deviation_ft=deviation,max_abs_deviation_ft=max(deviation,previous_y/.3048),
            correction_triggered=True,stable_duration_s=stable,complete=i==4,
            brake_left=left,brake_right=right,brake_system_mode=0,auto_brake_active=False)
        state=dict(flight_phase="SUCCESS" if i==4 else "CORRECTING",speed_kn=100,time=i*.5)
        records.append({"kind":"step","raw_action":action,"state_before":{"correction_triggered":i>1},
                        "result":{"state":state,"simulation":sim,"done":i==4}})
        previous_y=sim["y_m"]
    return records


@pytest.mark.parametrize("fault,gate",[("early","no_early_braking"),("speed","initial_condition_valid"),
    ("direction","differential_direction_correct"),("no_brakes","differential_direction_correct"),
    ("routing","brake_routing_valid"),("position","state_continuity"),
    ("recovery","recovered_within_30ft"),("hold","stable_recovery"),("automatic","brakes_are_correction_actuator")])
def test_evaluator_rejects_incomplete_or_spurious_recovery(fault,gate):
    scene=SceneRegistry().get("ground_direction");evaluator=RunEvaluator();context={"normalized_parameters":P}
    records=fixture_records()
    assert evaluator.evaluate(scene,records,"0.4.0","hash",context)["passed"]
    if fault=="early":records[1]["raw_action"]["brake_left"]=.1
    if fault=="speed":records[1]["result"]["simulation"]["initial_speed_kn"]=99
    if fault=="direction":records[2]["raw_action"].update(brake_left=0,brake_right=.4)
    if fault=="no_brakes":
        for r in records[1:]:r["raw_action"].update(brake_left=0,brake_right=0)
    if fault=="routing":records[2]["result"]["simulation"]["brake_left"]=0
    if fault=="position":records[2]["result"]["simulation"]["initial_y_m"]+=1
    if fault=="recovery":records[-1]["result"]["simulation"]["lateral_deviation_ft"]=31
    if fault=="hold":records[-1]["result"]["simulation"]["stable_duration_s"]=.9
    if fault=="automatic":records[2]["result"]["simulation"]["auto_brake_active"]=True
    result=evaluator.evaluate(scene,records,"0.4.0","hash",context)
    assert result["hard_gates"][gate] is False
    if fault=="hold":
        assert result["document_core_indicators"]["passed"] is True
        assert result["engineering_stability"]["passed"] is False
        assert result["passed"] is False


def test_full_correction_run_uses_own_contract_action_and_evaluator(tmp_path,monkeypatch):
    monkeypatch.setattr("multiflight.services.run_service.RUN_DIR",tmp_path)
    fixture=fixture_records();calls=[]
    class Simulator:
        def begin_run(self,*args,configuration,**kwargs):
            self.records=[];self.configuration=configuration
        def reset(self):self.records.append(fixture[0]);return fixture[0]["result"]
        def step(self,action):
            r=deepcopy(fixture[len(self.records)]);r["raw_action"]=action;self.records.append(r);return r["result"]
        def snapshot(self):return self.records
        def finish_run(self):pass
    class Executor:
        def submit(self,fn,*args):return fn(*args)
    def decide(**kw):
        action=fixture[len(calls)+1]["raw_action"];calls.append(kw)
        return {"answer":json.dumps(action)}
    sim=Simulator()
    service=RunService(jobs=JobStore(tmp_path/"jobs.db"),scenes=SceneRegistry(),prompts=PromptStore(tmp_path/"prompts.json"),
        compiler=PromptCompiler(),simulator=sim,dify=SimpleNamespace(run_agent=decide),evaluator=RunEvaluator(),
        executor=Executor(),execution_lock=threading.Lock())
    queued=service.start("ground_direction","0.4.0",parameters=P)
    job=service.jobs.get(queued["id"])
    assert job["status"]=="succeeded" and job["result"]["evaluation"]["test_point"]=="2-4"
    assert sim.configuration["correction_protocol"] and job["result"]["parameters"]==P
    assert len(calls)==job["result"]["dify"]["model_calls"]==4
    assert "50ft" in calls[0]["scene_prompt"]
    with pytest.raises(ValueError):service.start("ground_direction","0.3.0",parameters=P)


def test_negative_deviation_uses_opposite_brake_direction():
    records=fixture_records();parameters={**P,"initial_lateral_deviation_ft":-45,"initial_heading_deg":-2}
    for r in records[1:]:
        a=r["raw_action"];a["brake_left"],a["brake_right"]=a["brake_right"],a["brake_left"]
        s=r["result"]["simulation"]
        for key in ["initial_y_m","y_m","lateral_deviation_ft"]:s[key]=-s[key]
        s["brake_left"],s["brake_right"]=s["brake_right"],s["brake_left"]
    result=RunEvaluator().evaluate(SceneRegistry().get("ground_direction"),records,"0.4.0","hash",{"normalized_parameters":parameters})
    assert result["passed"]
