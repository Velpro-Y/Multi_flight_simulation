"""Reuse actual pre-failure Dify decisions only if reproduced states match."""
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from multiflight.main import run_service, jobs, executor

source=ROOT/'data/runs/run-84b7595c4925/decisions.json'
job=run_service.start('ground_direction','0.2.0',preparation={'replay_decisions_file':str(source)})
print(job['id'],flush=True)
try:
    for _ in range(240):
        job=jobs.get(job['id'])
        if job['status'] in {'succeeded','completed_with_failures','failed'}:
            result=job.get('result') or {}
            print(json.dumps({'id':job['id'],'status':job['status'],'error':job.get('error'),
                              'dify':result.get('dify'),'evaluation':result.get('evaluation')},ensure_ascii=False,indent=2),flush=True)
            sys.exit(0 if job['status']=='succeeded' else 1)
        time.sleep(2)
    raise TimeoutError('Realtime run timeout')
finally:
    executor.shutdown(wait=True)
