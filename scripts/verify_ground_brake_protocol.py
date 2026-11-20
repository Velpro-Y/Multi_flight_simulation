"""Exercise real MATLAB reset/step/brake routing with zero Dify calls."""
import json
import uuid
from pathlib import Path

from multiflight.simulation import SimulationManager
from multiflight.settings import RUN_DIR

rid='ground-brake-protocol-'+uuid.uuid4().hex[:10]
manager=SimulationManager()
manager.begin_run(rid,'ground_direction',configuration={'mode':'realtime','brake_protocol':True})
folder=RUN_DIR/rid
folder.mkdir(exist_ok=True)
checks={}
try:
    result=manager.reset()
    for _ in range(12):
        result=manager.step({'nose_wheel_deg':0,'throttle_left':.4,'throttle_right':.4,
                             'brake_left':0,'brake_right':0,'brake_system_mode':0,'auto_brake_armed':False})
        print('accelerate',result['state']['time'],result['state']['speed_kn'],flush=True)
        if result['state']['reached_5kn']:break
    checks['accelerated_to_5kn']=result['state']['reached_5kn']
    for name,fields in [
        ('left',{'brake_left':.2,'brake_right':0,'brake_system_mode':0,'auto_brake_armed':False}),
        ('auto',{'brake_left':0,'brake_right':0,'brake_system_mode':1,'auto_brake_armed':True}),
        ('right',{'brake_left':0,'brake_right':.2,'brake_system_mode':0,'auto_brake_armed':False})]:
        result=manager.step({'nose_wheel_deg':0,'throttle_left':0,'throttle_right':0,**fields})
        s=result['state'];expected=(.15,.15) if name=='auto' else (fields['brake_left'],fields['brake_right'])
        checks[name+'_routing']=abs(s['brake_left']-expected[0])<1e-7 and abs(s['brake_right']-expected[1])<1e-7
        checks[name+'_safe']=result['simulation']['safe']
        print(name,json.dumps(s,ensure_ascii=False),flush=True)
    records=manager.snapshot()
    checks['continuous_time']=all(abs(r['result']['state']['time']-r['state_before']['time']-.5)<1e-6
                                   for r in records if r['kind']=='step')
    report={'run_id':rid,'passed':all(checks.values()),'checks':checks,'dify_calls':0}
    (folder/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
finally:
    (folder/'records.json').write_text(json.dumps(manager.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')
    manager.finish_run()
