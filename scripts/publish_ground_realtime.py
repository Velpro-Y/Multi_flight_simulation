"""Publish only after the actual new-protocol run passes every gate."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from multiflight.db import JobStore
from multiflight.prompts import PromptCompiler, PromptStore
from multiflight.scene_registry import SceneRegistry

job=JobStore().get('run-54b2b6bae411'); result=job['result']
assert job['status']=='succeeded' and result['evaluation']['passed']
store=PromptStore(); artifact=PromptCompiler().compile(SceneRegistry().get('ground_direction'),'0.2.0')
assert artifact.prompt_hash==result['prompt']['prompt_hash']
store.attach_regression('ground_direction','0.2.0',{
    'passed':True,'validation_run':job['id'],'checks':result['evaluation']['hard_gates'],
    'kind':'new_control_protocol_validation',
    'note':'New direct-control protocol; not a same-protected-hash optimization comparison against 0.1.0.'})
store.publish('ground_direction','0.2.0','Validated 16 per-step Dify decisions; supersedes two-stage protocol')
print('ground_direction published=0.2.0')
