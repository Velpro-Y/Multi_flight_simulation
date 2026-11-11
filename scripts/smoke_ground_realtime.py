"""Validate incremental MATLAB state and changed controls without LLM costs."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from multiflight.simulation.ground_realtime import GroundRealtimeEnv

env = GroundRealtimeEnv("ground-rt-smoke-" + uuid.uuid4().hex[:6])
try:
    print(env.folder, flush=True)
    env.reset()
    for left in (0.4, 0.2):
        result = env.step({"nose_wheel_deg": 0, "throttle_left": left, "throttle_right": left})
        print(json.dumps(result["state"]), flush=True)
finally:
    env.close()
