"""Audit each model observation/action/result without more simulation calls."""
import csv
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--run-id',default='run-54b2b6bae411')
args=parser.parse_args()
folder=ROOT/'data/runs'/args.run_id
decisions=json.loads((folder/'decisions.json').read_text(encoding='utf-8'))
records=json.loads((folder/'records.json').read_text(encoding='utf-8'))
steps=[r for r in records if r['kind']=='step']
rows=[]
for d,r in zip(decisions,steps):
    state=d['state']; end=r['result']['state']
    rows.append({'step':d['index'],'decision_source':d['source'],
                 'observed_time_s':state['time'],'observed_speed_kn':state['speed_kn'],
                 'observed_heading_deg':state['heading_deg'],**d['action'],
                 'result_time_s':end['time'],'result_speed_kn':end['speed_kn'],
                 'result_heading_deg':end['heading_deg'],'actual_wheel_deg':end['wheel_deg'],
                 'on_ground':end['on_ground']})
with (folder/'decision_trace.csv').open('w',newline='',encoding='utf-8-sig') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
print(folder/'decision_trace.csv')
