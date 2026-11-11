"""Run a bounded MATLAB controller check with saved trim; makes no Dify calls."""

import argparse
import json
import logging
import math
import sqlite3
import uuid
from pathlib import Path

from multiflight.simulation.flight_env import FlightEnv
from multiflight.settings import STEP_TIME

parser = argparse.ArgumentParser()
parser.add_argument('--preparation', default='prep-325d88de172e')
parser.add_argument('--max-time', type=float, default=160.)
args = parser.parse_args()
logging.basicConfig(level=logging.WARNING)
root = Path(__file__).resolve().parents[1]
con = sqlite3.connect((root/'data/multiflight.db').as_uri()+'?mode=ro', uri=True)
cfg = json.loads(con.execute('SELECT result_json FROM jobs WHERE id=?', (args.preparation,)).fetchone()[0])
con.close()
rid = 'controller-check-' + uuid.uuid4().hex[:10]
folder = root/'data/runs'/rid
folder.mkdir()
env = FlightEnv(run_id=rid, configuration=cfg)
env.state_file = str(folder/'state.mat')
records = []
reason = 'time_limit'
try:
    result = env.reset()
    records.append({'kind':'reset', 'result':result})
    last_phase = None
    for step in range(int(args.max_time / STEP_TIME)):
        phase = env.flight_phase
        profile = env.twin_descent_trim if phase=='TWIN_DESCENT' else (env.engine_out_descent_trim if phase=='ENGINE_OUT_DESCENT' else env.engine_out_climb_trim)
        action = {k:profile[k] for k in ['aileron','elevator','rudder','throttle_left','throttle_right']}
        before = env.get_state()
        result = env.step(action)
        records.append({'kind':'step','state_before':before,'raw_action':action,'applied_action':result['applied_action'],'result':result})
        s = result['state']
        if s['flight_phase'] != last_phase or step % 10 == 0:
            print(rid, s['time'], s['flight_phase'], round(s['altitude'],2), round(math.degrees(s['roll']),2), flush=True)
            last_phase = s['flight_phase']
        if s['altitude'] <= 0:
            reason = 'ground_contact'; break
        if abs(s['roll']) > .6:
            reason = 'roll_divergence'; break
        if result['done']:
            reason = result['event']; break
finally:
    env.close()
    (folder/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    ss = [r['result']['state'] for r in records]
    report = {'id':rid,'preparation_id':args.preparation,'step_time_s':STEP_TIME,'reason':reason,
              'final_state':ss[-1], 'min_altitude_ft':min(s['altitude'] for s in ss),
              'max_abs_roll_deg':max(abs(math.degrees(s['roll'])) for s in ss),
              'min_airspeed_ft_s':min(s['airspeed'] for s in ss),'dify_calls':0}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
