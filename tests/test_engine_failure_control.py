from copy import deepcopy

import pytest

from multiflight.evaluation import RunEvaluator
from multiflight.scene_registry import SceneRegistry
from multiflight.settings import ENGINE_OUT_CLIMB_TRIM, ENGINE_OUT_DESCENT_TRIM
from multiflight.simulation.flight_env import FlightEnv


def controller():
    env = FlightEnv.__new__(FlightEnv)
    env.engine_out_descent_trim = deepcopy(ENGINE_OUT_DESCENT_TRIM)
    env.engine_out_descent_trim['throttle_right'] = .09
    env.engine_out_climb_trim = deepcopy(ENGINE_OUT_CLIMB_TRIM)
    env.go_around_time = 0.
    env._reset_single_engine_stabilizer(env.engine_out_descent_trim)
    return env


def trim_state(env):
    return {**env.engine_out_descent_trim, 'roll_rate': 0., 'pitch_rate': 0., 'yaw_rate': 0.}


def test_descent_preserves_low_throttle_trim():
    env = controller()
    result = env._single_engine_stabilizer(trim_state(env))
    assert result['throttle_right'] == pytest.approx(.09)


def test_first_go_around_interval_builds_thrust():
    env = controller()
    result = env._single_engine_stabilizer(trim_state(env), go_around=True)
    assert result['trim_blend'] == pytest.approx(1 / 3)
    assert .09 < result['throttle_right'] <= .25
    assert result['throttle_left'] == 0.


def test_airspeed_deficit_does_not_raise_pitch_target():
    env = controller()
    env.go_around_time = 6.
    nominal = trim_state(env)
    nominal.update(airspeed=env.engine_out_climb_trim['airspeed'], vertical_speed=env.engine_out_climb_trim['vertical_speed'])
    target = env._single_engine_stabilizer(nominal, True)['target_pitch']
    low_speed = {**nominal, 'airspeed': nominal['airspeed'] - 10}
    assert env._single_engine_stabilizer(low_speed, True)['target_pitch'] < target


@pytest.mark.parametrize('altitude', [-1., 0., float('nan')])
def test_invalid_altitude_fails_state_evaluation(altitude):
    step = {'result': {'state': {'altitude': altitude, 'airspeed': 140., 'roll': 0., 'pitch': .1}}}
    assert not RunEvaluator._state_safe(SceneRegistry().get('engine_failure'), [step])


def test_terminal_result_is_returned_without_advancing_matlab(monkeypatch, tmp_path):
    class FakeEngine:
        workspace = {}

        def __init__(self):
            self.calls = 0

        def eval(self, *args, **kwargs):
            self.calls += 1
            return 0

    engine = FakeEngine()
    monkeypatch.setattr('multiflight.simulation.flight_env.get_engine', lambda: engine)
    env = FlightEnv(run_id='test-terminal')
    env.log_file = tmp_path / 'telemetry.csv'
    env.state_file = str(tmp_path / 'state.mat')
    state = {'time': 2., 'altitude': -1., 'airspeed': 140., 'vertical_speed': -10.,
             'roll': 0., 'pitch': .1, 'yaw': 0., 'roll_rate': 0., 'pitch_rate': 0., 'yaw_rate': 0.,
             'left_engine_fail': False, 'flight_phase': 'TWIN_DESCENT'}
    env.get_state = lambda: deepcopy(state)
    action = {k: 0. for k in ['aileron', 'elevator', 'rudder', 'throttle_left', 'throttle_right']}
    result = env.step(action)
    assert result['done'] and result['event'] == 'GROUND_CONTACT'
    calls = engine.calls
    assert env.step(action) == result
    assert engine.calls == calls
