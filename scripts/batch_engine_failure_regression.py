"""Bounded scene-one MATLAB regression matrix; no Dify calls. Supports resume."""

import argparse
import csv
import hashlib
import json
import logging
import math
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from multiflight.db import JobStore
from multiflight.scene_registry import SceneRegistry
from multiflight.schemas import EngineFailureParameters
from multiflight.services.preparation_service import PreparationService
from multiflight.settings import STEP_TIME
from multiflight.simulation.flight_env import FlightEnv
from multiflight.simulation.flight_safety import state_limit_reason
from multiflight.trimming import MatlabTrimProvider


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', default='data/runs/scene1-regression-20261111')
parser.add_argument('--only', nargs='*', help='Run/resume selected case IDs')
parser.add_argument('--retry-failed', action='store_true')
args = parser.parse_args()
OUT = (ROOT / args.output).resolve()
OUT.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.WARNING)


def case(cid, h, speed, fail, go, target, limit=300., expected='GO_AROUND_SUCCESS'):
    p = EngineFailureParameters(initial_altitude_ft=h, initial_airspeed_ft_s=speed,
                                engine_failure_altitude_ft=fail, go_around_altitude_ft=go,
                                target_altitude_ft=target, max_simulation_time_s=limit).model_dump()
    return {'case_id': cid, 'parameters': p, 'expected_event': expected}


CASES = [
    case('C01', 500, 148.911745406824, 300, 200, 500),
    case('C02', 400, 135, 250, 150, 400),
    case('C03', 400, 140, 250, 150, 400),
    case('C04', 400, 150, 250, 150, 400),
    case('C05', 400, 160, 250, 150, 400),
    case('C06', 400, 165, 250, 150, 400),
    case('C07', 400, 140, 250, 100, 400),
    case('C08', 400, 150, 250, 100, 400),
    case('C09', 700, 160, 400, 300, 500),
    case('C10', 1000, 165, 800, 700, 1000),
    case('C11', 1000, 140, 800, 200, 500),
    case('C12', 600, 145, 350, 220, 800),
    case('C13', 500, 150, 490, 480, 500),
    case('C14', 1000, 150, 800, 700, 1500),
    case('C15', 500, 148.911745406824, 300, 200, 500, limit=60., expected='TIME_LIMIT_REACHED'),
]


def save(path, obj):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def control_hash():
    paths = ['src/multiflight/settings.py', 'src/multiflight/simulation/flight_env.py',
             'src/multiflight/simulation/engine_failure_control.py',
             'src/multiflight/simulation/flight_safety.py', 'simulink/beaver_agent_env.slx']
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


HASHES = control_hash()
matrix_path = OUT / 'matrix.json'
if matrix_path.exists():
    assert json.loads(matrix_path.read_text(encoding='utf-8')) == CASES, 'Do not silently alter a started matrix'
else:
    save(matrix_path, CASES)

store = JobStore()
registry = SceneRegistry()
safety = registry.get('engine_failure').safety


class CachedTrimmer:
    def __init__(self):
        self.cache = {}
        import sqlite3
        con = sqlite3.connect((ROOT / 'data/multiflight.db').as_uri() + '?mode=ro', uri=True)
        for (raw,) in con.execute("SELECT result_json FROM jobs WHERE kind='preparation' AND status='succeeded'"):
            value = json.loads(raw or '{}')
            p = value.get('normalized_parameters')
            if p and value.get('trim', {}).get('converged'):
                self.cache[self.key(p)] = deepcopy(value['trim'])
        con.close()

    @staticmethod
    def key(p):
        return tuple(p[k] for k in ['initial_altitude_ft', 'initial_airspeed_ft_s',
                                    'engine_failure_altitude_ft', 'go_around_altitude_ft'])

    def prepare_engine_failure(self, p):
        key = self.key(p)
        if key not in self.cache:
            self.cache[key] = MatlabTrimProvider().prepare_engine_failure(p)
        return deepcopy(self.cache[key])


preparer = PreparationService(jobs=store, scenes=registry, trimmer=CachedTrimmer(), execution_lock=threading.Lock())


def aggregate():
    reports = []
    for c in CASES:
        path = OUT / c['case_id'] / 'report.json'
        if path.exists():
            reports.append(json.loads(path.read_text(encoding='utf-8')))
    save(OUT / 'summary.json', reports)
    if reports:
        rows = [{k: v for k, v in r.items() if k not in ['source_hashes', 'final_state', 'parameters', 'phase_trace']}
                | r['parameters'] for r in reports]
        with (OUT / 'summary.csv').open('w', encoding='utf-8-sig', newline='') as f:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            writer = csv.DictWriter(f, keys)
            writer.writeheader()
            writer.writerows(rows)
    return reports


for c in CASES:
    cid = c['case_id']
    if args.only and cid not in args.only:
        continue
    folder = OUT / cid
    folder.mkdir(exist_ok=True)
    if (folder / 'report.json').exists():
        previous = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
        if not args.retry_failed or previous.get('expectation_met'):
            print('SKIP', cid, previous['event'], flush=True)
            continue
        raise RuntimeError('Use a new --output for modified-code retests; preserve failed evidence')
    started = time.monotonic()
    records, config, env = [], None, None
    error, event = None, 'EXECUTION_ERROR'
    print('START', cid, json.dumps(c['parameters']), flush=True)
    try:
        config_path = folder / 'configuration.json'
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding='utf-8'))
        else:
            config = preparer.prepare('engine_failure', EngineFailureParameters(**c['parameters']))
            save(config_path, config)
        env = FlightEnv(run_id=OUT.name + '-' + cid, configuration=config)
        env.state_file = str(folder / 'state.mat')
        result = env.reset()
        records.append({'sequence': 0, 'kind': 'reset', 'result': deepcopy(result)})
        phase_before = None
        for index in range(math.ceil(c['parameters']['max_simulation_time_s'] / STEP_TIME)):
            before = deepcopy(env.get_state())
            profile = env.twin_descent_trim if env.flight_phase == 'TWIN_DESCENT' else (
                env.engine_out_descent_trim if env.flight_phase == 'ENGINE_OUT_DESCENT' else env.engine_out_climb_trim)
            action = {k: profile[k] for k in ['aileron', 'elevator', 'rudder', 'throttle_left', 'throttle_right']}
            result = env.step(action)
            records.append({'sequence': len(records), 'kind': 'step', 'state_before': before,
                            'raw_action': deepcopy(action), 'applied_action': deepcopy(result['applied_action']),
                            'result': deepcopy(result)})
            save(folder / 'records.json', records)
            s = result['state']
            if s['flight_phase'] != phase_before or index % 20 == 0:
                print('STATE', cid, s['time'], round(s['altitude'], 2), s['flight_phase'], flush=True)
                phase_before = s['flight_phase']
            if result['done']:
                event = result['event']
                break
        else:
            event = 'HARNESS_TIME_LIMIT'
    except Exception as exc:
        error = str(exc)
    finally:
        if env is not None:
            env.close()
        ss = [r['result']['state'] for r in records]
        safe = bool(ss) and all(state_limit_reason(s, safety) is None for s in ss)
        steps = [r for r in records if r['kind'] == 'step']
        phases = list(dict.fromkeys(s['flight_phase'] for s in ss))
        complete = event == 'GO_AROUND_SUCCESS'
        report = {'case_id': cid, 'parameters': c['parameters'], 'expected_event': c['expected_event'],
                  'event': event, 'expectation_met': event == c['expected_event'] and safe,
                  'completed': complete, 'state_safe': safe, 'error': error,
                  'preparation_id': config.get('preparation_id') if config else None,
                  'steps': len(steps), 'step_time_s': STEP_TIME,
                  'dify_calls': 0, 'wall_time_s': round(time.monotonic() - started, 2),
                  'minimum_altitude_ft': min(s['altitude'] for s in ss) if ss else None,
                  'max_abs_roll_deg': max(abs(math.degrees(s['roll'])) for s in ss) if ss else None,
                  'min_airspeed_ft_s': min(s['airspeed'] for s in ss) if ss else None,
                  'final_state': ss[-1] if ss else None, 'phase_trace': phases,
                  'source_hashes': HASHES, 'created_at': datetime.now(timezone.utc).isoformat()}
        save(folder / 'report.json', report)
        aggregate()
        print('RESULT', cid, json.dumps({k: report[k] for k in ['event', 'expectation_met', 'steps',
              'minimum_altitude_ft', 'max_abs_roll_deg', 'wall_time_s', 'error']}), flush=True)

summary = aggregate()
print('FINISHED', json.dumps({'cases': len(summary), 'expectations_met': sum(r['expectation_met'] for r in summary),
                              'completed': sum(r['completed'] for r in summary)}), flush=True)
