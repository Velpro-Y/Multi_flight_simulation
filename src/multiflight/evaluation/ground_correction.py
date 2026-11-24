"""Evaluate test point 2-4 independently from low-speed turning."""
from math import ceil, isfinite

from ..schemas import GroundCorrectionParameters
from ..simulation.ground_realtime import GroundCorrectionAction


def evaluate_correction(scene, records, version, prompt_hash, runtime_context=None):
    p=GroundCorrectionParameters.model_validate((runtime_context or {}).get("normalized_parameters", {}))
    steps=[r for r in records if r.get("kind")=="step"]
    resets=[r for r in records if r.get("kind")=="reset"]
    valid=True;early=False;routing=True;isolated=True;continuous=True;first_direction=None
    triggered=abs(p.initial_lateral_deviation_ft)>50
    previous=dict(time_s=0,x_m=0,y_m=p.initial_lateral_deviation_ft*.3048,speed_kn=100)
    sims=[]
    for record in steps:
        s=record["result"].get("simulation",{});sims.append(s)
        try:
            a=GroundCorrectionAction.model_validate(record["raw_action"])
            early |= (not triggered and (a.brake_left>0 or a.brake_right>0))
            if first_direction is None and abs(a.brake_left-a.brake_right)>1e-8:
                first_direction=(a.brake_left-a.brake_right)*previous["y_m"]>0
            routing &= (abs(s["brake_left"]-a.brake_left)<1e-6 and abs(s["brake_right"]-a.brake_right)<1e-6)
            isolated &= (s["brake_system_mode"]==0 and not s["auto_brake_active"] and s["max_wheel_deg"]<1e-5)
            gap=s["start_time_s"]-previous["time_s"]
            motion=max(previous["speed_kn"],s["initial_speed_kn"])*.5144444444*max(gap,0)+1e-5
            continuous &= (-1e-9<=gap<=.001 and 0<s["time_s"]-previous["time_s"]<=.5001
                and abs(s["initial_x_m"]-previous["x_m"])<=motion
                and abs(s["initial_y_m"]-previous["y_m"])<=motion
                and abs(s["initial_speed_kn"]-previous["speed_kn"])<=10*max(gap,0)+1e-5)
            expected=triggered or s["max_abs_deviation_ft"]>50
            valid &= bool(s["correction_triggered"])==expected
            triggered=expected
        except (KeyError,TypeError,ValueError):
            valid=False;routing=False;continuous=False
        previous=s
    final=sims[-1] if sims else {}
    first=sims[0] if sims else {}
    def finite_within(key,bound):
        value=final.get(key,float("inf"))
        return isfinite(value) and abs(value)<=bound+1e-8
    gates={
        "reset_and_steps": len(resets)==1 and 1<=len(steps)<=ceil(p.max_simulation_time_s/.5),
        "initial_condition_valid": abs(first.get("initial_speed_kn",0)-100)<.001
            and abs(first.get("initial_y_m",float("inf"))-p.initial_lateral_deviation_ft*.3048)<1e-5,
        "format_valid": valid and bool(steps),
        "trigger_50ft_observed": triggered,
        "no_early_braking": not early,
        "differential_direction_correct": first_direction is True,
        "brake_routing_valid": routing and bool(steps),
        "brakes_are_correction_actuator": isolated and bool(steps),
        "state_continuity": continuous and bool(steps),
        "state_safe": bool(sims) and all(s.get("safe") and s.get("on_ground") for s in sims),
        "recovered_within_30ft": finite_within("lateral_deviation_ft",30),
        "stable_recovery": final.get("stable_duration_s",0)>=1 and finite_within("heading_deg",3)
            and finite_within("yaw_rate_deg_s",1) and finite_within("lateral_velocity_m_s",.75),
        "completed": bool(final.get("complete") and steps[-1]["result"].get("done"))
            and final.get("time_s",float("inf"))<=p.max_simulation_time_s+1e-6,
    }
    core={"trigger_beyond_50ft":gates["trigger_50ft_observed"],
          "correct_initial_brake_direction":gates["differential_direction_correct"],
          "final_deviation_within_30ft":gates["recovered_within_30ft"]}
    return {"scene_id":scene.scene_id,"experiment":"brake_correction","test_point":"2-4",
            "prompt_version":version,"prompt_hash":prompt_hash,"parameters":p.model_dump(),
            "passed":all(gates.values()),"hard_gates":gates,
            "failure_labels":[k.upper() for k,v in gates.items() if not v],
            "document_core_indicators":{**core,"passed":all(core.values())},
            "engineering_stability":{"heading_tolerance_deg":3,"yaw_rate_tolerance_deg_s":1,
                "lateral_velocity_tolerance_m_s":.75,"hold_time_s":1,"passed":gates["stable_recovery"]},
            "metrics":{"steps":len(steps),"score":100*sum(gates.values())/len(gates),
                       "time_s":final.get("time_s"),"final_deviation_ft":final.get("lateral_deviation_ft"),
                       "peak_abs_deviation_ft":max((s.get("max_abs_deviation_ft",0) for s in sims),default=0),
                       "final_speed_kn":final.get("speed_kn"),"stable_duration_s":final.get("stable_duration_s")},
            "scope":"原生6DOF模型的试验点2-4功能映射：100kn，50ft触发，30ft回收并稳定1s；非原大型机重量重心验收"}
