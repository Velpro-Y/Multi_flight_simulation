"""Dify controls each 0.5 simulated seconds; only rate/limit protection below it."""

import json
import os
import subprocess
import time
import uuid

from pydantic import BaseModel, ConfigDict, Field

from ..settings import PROJECT_ROOT, RUN_DIR


class GroundRealtimeAction(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    nose_wheel_deg: float = Field(ge=0, le=75)
    throttle_left: float = Field(ge=0, le=0.4)
    throttle_right: float = Field(ge=0, le=0.4)


class GroundRealtimeEnv:
    def __init__(self, run_id, configuration=None):
        self.folder = RUN_DIR / run_id / ("realtime-" + uuid.uuid4().hex[:8])
        self.folder.mkdir(parents=True)
        self.state = None
        self.worker = None
        self.log = None
        self.sequence = 0
        self.reached_5 = False

    def _wait(self, name, timeout=90):
        path = self.folder / name
        deadline = time.monotonic()+timeout
        while not path.exists():
            if self.worker.poll() is not None:
                raise RuntimeError(f"MATLAB worker exited; inspect {self.folder / 'matlab.log'}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"MATLAB response timed out: {name}")
            time.sleep(0.1)
        response = json.loads(path.read_text(encoding="utf-8"))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response

    def reset(self):
        quote = lambda p: str(p).replace("'", "''")
        command = (f"addpath('{quote(PROJECT_ROOT / 'simulink03')}'); "
                   f"ground_realtime_worker('{quote(self.folder)}')")
        self.log = (self.folder / "matlab.log").open("w", encoding="utf-8")
        self.worker = subprocess.Popen(
            [os.getenv("MATLAB_EXECUTABLE", "D:/soft/MATLAB/bin/matlab.exe"), "-batch", command],
            cwd=str(self.folder), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._wait("ready.json")
        self.state = {"flight_phase": "READY", "time": 0, "speed_kn": 0,
                      "heading_deg": 0, "yaw_rate_deg_s": 0, "wheel_deg": 0,
                      "x_m": 0, "y_m": 0, "roll_deg": 0,
                      "on_ground": True, "reached_5kn": False}
        return {"state": self.state, "done": False, "event": "REALTIME_READY"}

    def get_state(self):
        return self.state

    def step(self, raw_action):
        action = GroundRealtimeAction.model_validate(raw_action)
        if self.state is None or self.state["flight_phase"] in {"SUCCESS", "FAILED"}:
            raise ValueError("Reset required or run already finished")
        if not self.reached_5 and action.nose_wheel_deg != 0:
            raise ValueError("Must reach 5kn before steering")
        self.sequence += 1
        path = self.folder / f"request_{self.sequence:03d}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(action.model_dump_json(), encoding="utf-8")
        temporary.replace(path)
        sim = self._wait(f"response_{self.sequence:03d}.json", timeout=90)
        self.reached_5 |= sim["speed_kn"] >= 5
        done = sim["complete"] or not sim["safe"] or self.sequence >= 40
        phase = "SUCCESS" if sim["complete"] else "FAILED" if done else "TURN" if self.reached_5 else "ACCELERATE"
        self.state = {"flight_phase": phase, "time": sim["time_s"],
                      **{k: sim[k] for k in ["speed_kn", "heading_deg", "yaw_rate_deg_s", "wheel_deg", "x_m", "y_m", "roll_deg", "on_ground"]},
                      "reached_5kn": self.reached_5}
        return {"state": self.state, "done": done, "event": phase,
                "applied_action": action.model_dump(),
                "simulation": {k: v for k, v in sim.items() if k != "trajectory"},
                "simulation_file": str(self.folder / f"response_{self.sequence:03d}.json")}

    def close(self):
        (self.folder / "stop.flag").write_text("stop", encoding="utf-8")
        if self.worker is not None:
            try: self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired: self.worker.terminate()
        if self.log: self.log.close()
