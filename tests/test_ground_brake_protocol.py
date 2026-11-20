from copy import deepcopy

import pytest
from pydantic import ValidationError

from multiflight.evaluation import RunEvaluator
from multiflight.prompts import PromptCompiler, PromptStore
from multiflight.scene_registry import SceneRegistry
from multiflight.simulation.ground_realtime import GroundBrakeAction, GroundRealtimeEnv


def test_brake_protocol_is_candidate_and_old_default_is_preserved(tmp_path):
    versions=PromptStore(tmp_path/'registry.json').list_versions('ground_direction')
    assert versions['published']=='0.2.0'
    assert versions['versions']['0.3.0']['status']=='candidate'
    prompt=PromptCompiler().compile(SceneRegistry().get('ground_direction'),'0.3.0')
    assert 'brake_left' in prompt.text and 'steering_limit_deg' in prompt.text
    assert '随速限角' in prompt.text


@pytest.mark.parametrize('fields', [dict(brake_left=1.1),dict(brake_right=-.1),dict(brake_left=float('nan')),
                                  dict(brake_system_mode=2),dict(brake_system_mode=1,brake_left=.1)])
def test_brake_action_rejects_invalid_and_conflicting_inputs(fields):
    with pytest.raises(ValidationError):
        GroundBrakeAction(nose_wheel_deg=0,throttle_left=0,throttle_right=0,**fields)


def test_actual_auto_braking_is_recorded_separately_from_manual_request(tmp_path,monkeypatch):
    monkeypatch.setattr('multiflight.simulation.ground_realtime.RUN_DIR',tmp_path)
    env=GroundRealtimeEnv('test',{'brake_protocol':True})
    env.state={'flight_phase':'READY'}
    sim=dict(time_s=.5,speed_kn=0,heading_deg=0,yaw_rate_deg_s=0,wheel_deg=0,x_m=0,y_m=0,roll_deg=0,
             on_ground=True,safe=True,complete=False,brake_left=.15,brake_right=.15,
             brake_system_mode=1,auto_brake_armed=True,auto_brake_active=True,steering_limit_deg=75)
    monkeypatch.setattr(env,'_wait',lambda *args,**kwargs:sim)
    result=env.step(dict(nose_wheel_deg=0,throttle_left=0,throttle_right=0,
                         brake_system_mode=1,auto_brake_armed=True))
    assert result['applied_action']['brake_left']==.15
    assert result['state']['auto_brake_active'] is True
    assert result['state']['auto_brake_used'] is True
    assert 'brake_left' in (env.folder/'request_001.json').read_text()


def fixture_records():
    records=[{'kind':'reset','result':{'state':{'flight_phase':'READY'}}}]
    for i in range(3):
        action=dict(nose_wheel_deg=0,throttle_left=0,throttle_right=0,brake_left=0,brake_right=0,
                    brake_system_mode=1,auto_brake_armed=True)
        sim=dict(time_s=(i+1)*.5,start_time_s=i*.5,x_m=0,y_m=0,speed_kn=0,initial_x_m=0,initial_y_m=0,
                 initial_speed_kn=0,safe=True,on_ground=True,max_wheel_deg=75,complete=i==2,
                 brake_left=.15,brake_right=.15,brake_system_mode=1,auto_brake_active=True,
                 auto_brake_min_level=.15,max_steering_excess_deg=0)
        records.append({'kind':'step','state_before':{'reached_5kn':True},'raw_action':action,
                        'result':{'done':i==2,'state':{'flight_phase':'TURN'},'simulation':sim}})
    return records


def test_brake_evaluation_detects_original_selector_failure_and_oversteering():
    scene=SceneRegistry().get('ground_direction');records=fixture_records()
    assert RunEvaluator().evaluate(scene,records,'0.3.0','hash')['passed']
    bad=deepcopy(records);bad[1]['result']['simulation']['brake_left']=0
    assert not RunEvaluator().evaluate(scene,bad,'0.3.0','hash')['hard_gates']['brake_routing_valid']
    bad=deepcopy(records);bad[1]['result']['simulation']['max_steering_excess_deg']=2
    assert not RunEvaluator().evaluate(scene,bad,'0.3.0','hash')['hard_gates']['steering_authority_valid']


def test_response_parser_accepts_one_action_with_surrounding_text():
    from multiflight.services.run_service import _parse_realtime_action
    text='先根据当前状态加速。\n```json\n{"nose_wheel_deg":0,"throttle_left":0.4,"throttle_right":0.4}\n```'
    assert _parse_realtime_action(text,GroundBrakeAction).throttle_left==.4


def test_response_parser_rejects_ambiguous_or_invalid_actions():
    from multiflight.services.run_service import _parse_realtime_action
    one='{"nose_wheel_deg":0,"throttle_left":0.4,"throttle_right":0.4}'
    with pytest.raises(ValueError):_parse_realtime_action(one+'\n'+one,GroundBrakeAction)
    with pytest.raises(ValidationError):
        _parse_realtime_action('{"nose_wheel_deg":0,"throttle_left":2,"throttle_right":0}',GroundBrakeAction)
