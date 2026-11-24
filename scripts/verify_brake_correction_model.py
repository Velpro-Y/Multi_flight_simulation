"""Model-only reference and coast checks for scene-three test point 2-4."""
import argparse
import json
import uuid

from multiflight.schemas import GroundCorrectionParameters
from multiflight.settings import RUN_DIR
from multiflight.simulation import SimulationManager
from multiflight.evaluation import RunEvaluator
from multiflight.scene_registry import SceneRegistry


def run(mode):
    parameters=GroundCorrectionParameters(max_simulation_time_s=5 if mode=="coast" else 20).model_dump()
    rid="brake-correction-"+mode+"-"+uuid.uuid4().hex[:8]
    folder=RUN_DIR/rid;folder.mkdir(parents=True)
    manager=SimulationManager();error=None;result={}
    try:
        manager.begin_run(rid,"ground_direction",configuration={"mode":"realtime","brake_protocol":True,
            "correction_protocol":True,"normalized_parameters":parameters})
        result=manager.reset()
        for index in range(40):
            s=result["state"];demand=0.
            if mode=="reference" and s["correction_triggered"]:
                predicted=s["lateral_deviation_ft"]+2*s["lateral_velocity_m_s"]/.3048
                desired=max(-6,min(6,-.3*(predicted-(15 if s["lateral_deviation_ft"]>0 else -15))))
                demand=max(-.8,min(.8,.12*(s["heading_deg"]-desired)+.4*s["yaw_rate_deg_s"]))
            result=manager.step(dict(nose_wheel_deg=0,throttle_left=0,throttle_right=0,
                                    brake_left=max(demand,0),brake_right=max(-demand,0),
                                    brake_system_mode=0,auto_brake_armed=False))
            s=result["state"]
            if index%4==0 or result["done"]:
                print(mode,index+1,s["time"],round(s["lateral_deviation_ft"],3),round(s["heading_deg"],3),
                      round(s["yaw_rate_deg_s"],3),round(s["stable_duration_s"],3),flush=True)
            if result["done"]:break
    except Exception as exc:error=str(exc)
    finally:
        records=manager.snapshot()
        (folder/"records.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
        manager.finish_run()
    steps=[r for r in records if r.get("kind")=="step"]
    evaluation=RunEvaluator().evaluate(SceneRegistry().get("ground_direction"),records,"0.4.0","model_test",
                                      {"normalized_parameters":parameters})
    checks={"initial_speed_100kn":bool(steps) and abs(steps[0]["result"]["simulation"]["initial_speed_kn"]-100)<.001,
            "safe_and_grounded":bool(steps) and all(r["result"]["simulation"]["safe"] and r["result"]["simulation"]["on_ground"] for r in steps)}
    if mode=="reference":checks["correction_passed"]=evaluation["passed"]
    else:checks["coast_still_outside_target"]=bool(steps) and abs(result["state"]["lateral_deviation_ft"])>30 and abs(result["state"]["time"]-5)<1e-6
    (folder/"evaluation.json").write_text(json.dumps(evaluation,ensure_ascii=False,indent=2),encoding="utf-8")
    report={"run_id":rid,"parameters":parameters,"mode":mode,"decision_source":"model_test_reference" if mode=="reference" else "zero_controls",
            "dify_calls":0,"error":error,"final":result,
            "checks":checks,"passed":not error and all(checks.values())}
    (folder/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="final"},ensure_ascii=False),flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--mode",choices=["reference","coast"],default="reference")
    args=parser.parse_args();report=run(args.mode)
    raise SystemExit(0 if report["passed"] else 1)
