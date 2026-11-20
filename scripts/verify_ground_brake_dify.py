"""One fresh Dify run covering manual and automatic braking before a U-turn."""
import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]
query=('本轮验证刹车控制：达到5kn后，若manual_brake_used=false，依据实时状态使用一次非零右主轮手动刹车并观察响应；'
       '若auto_brake_used=false，切换自动模式并预位，读取实际auto_brake_active和左右0.15确认；'
       '两项累计标记均true后释放刹车并恢复手动模式，完成右转掉头。时机和大小由你决定，避免刹停。')
with httpx.Client(timeout=20,trust_env=False) as c:
    r=c.post('http://127.0.0.1:8000/api/runs',json={'scene_id':'ground_direction','prompt_version':'0.3.0','query':query})
    r.raise_for_status();rid=r.json()['id'];print('RUN_ID='+rid,flush=True)
last=None
for _ in range(180):
    con=sqlite3.connect((ROOT/'data/multiflight.db').as_uri()+'?mode=ro',uri=True)
    row=con.execute('select status,message,result_json,error from jobs where id=?',(rid,)).fetchone();con.close()
    if row[1]!=last:print(row[0],row[1],flush=True);last=row[1]
    if row[0] in ['succeeded','completed_with_failures','failed']:
        z=json.loads(row[2] or '{}');folder=ROOT/'data/runs'/rid
        records=json.loads((folder/'records.json').read_text(encoding='utf-8')) if (folder/'records.json').exists() else []
        steps=[r for r in records if r['kind']=='step']
        manual=any(r['raw_action'].get('brake_system_mode',0)==0 and r['applied_action'].get('brake_right',0)>0 for r in steps)
        auto=any(r['result']['state'].get('auto_brake_active') and abs(r['applied_action'].get('brake_left',0)-.15)<1e-6
                 and abs(r['applied_action'].get('brake_right',0)-.15)<1e-6 for r in steps)
        report={'run_id':rid,'status':row[0],'error':row[3],'query':query,'manual_right_brake_exercised':manual,
                'auto_brake_exercised':auto,'evaluation':z.get('evaluation'),'dify':z.get('dify')}
        report['coverage_passed']=bool(manual and auto and (z.get('evaluation') or {}).get('passed'))
        (folder/'brake_coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
        break
    time.sleep(5)
else:
    raise TimeoutError('Dify braking coverage run still active after 900 seconds')
