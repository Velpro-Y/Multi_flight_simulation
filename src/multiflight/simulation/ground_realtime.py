"""Dify controls each 0.5 simulated seconds; only rate/limit protection below it."""

import json
import math
import os
import subprocess
import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..settings import PROJECT_ROOT, RUN_DIR
from ..schemas import GroundDirectionParameters


class GroundRealtimeAction(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    nose_wheel_deg: float = Field(ge=0, le=75)
    throttle_left: float = Field(ge=0, le=0.4)
    throttle_right: float = Field(ge=0, le=0.4)


class GroundBrakeAction(GroundRealtimeAction):
    brake_left: float = Field(default=0, ge=0, le=1)
    brake_right: float = Field(default=0, ge=0, le=1)
    brake_system_mode: Literal[0, 1] = 0
    auto_brake_armed: bool = False

    @model_validator(mode="after")
    def exclusive_braking(self):
        if self.brake_system_mode == 1 and (self.brake_left != 0 or self.brake_right != 0):
            raise ValueError("自动刹车模式下左右手动刹车必须为0")
        return self


class GroundRealtimeEnv:
    def __init__(self, run_id, configuration=None):
        self.brake_protocol = bool((configuration or {}).get("brake_protocol"))
        self.parameters = GroundDirectionParameters.model_validate(
            (configuration or {}).get("normalized_parameters", {})
        )
        self.max_steps = math.ceil(self.parameters.max_simulation_time_s / .5)
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
        (self.folder / "configuration.json").write_text(
            self.parameters.model_dump_json(), encoding="utf-8"
        )
        quote = lambda p: str(p).replace("'", "''")
        protocol = ", 'brake'" if self.brake_protocol else ""
        command = (f"addpath('{quote(PROJECT_ROOT / 'simulink03')}'); "
                   f"ground_realtime_worker('{quote(self.folder)}'{protocol})")
        self.log = (self.folder / "matlab.log").open("w", encoding="utf-8")
        self.worker = subprocess.Popen(
            [os.getenv("MATLAB_EXECUTABLE", "D:/soft/MATLAB/bin/matlab.exe"), "-batch", command],
            cwd=str(self.folder), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Cold MATLAB/Simulink initialization can exceed 90 seconds for either model.
        self._wait("ready.json", timeout=180)
        self.reached_5 = self.parameters.initial_speed_kn >= 5
        self.sequence = 0
        self.state = {"flight_phase": "READY", "time": 0, "speed_kn": self.parameters.initial_speed_kn,
                      "heading_deg": 0, "yaw_rate_deg_s": 0, "wheel_deg": 0,
                      "x_m": 0, "y_m": 0, "roll_deg": 0,
                      "on_ground": True, "reached_5kn": self.reached_5,
                      "target_nose_wheel_deg": self.parameters.target_nose_wheel_deg,
                      "target_heading_change_deg": self.parameters.target_heading_change_deg,
                      "max_simulation_time_s": self.parameters.max_simulation_time_s}
        if self.brake_protocol:
            self.state.update(brake_left=0., brake_right=0., brake_system_mode=0,
                              auto_brake_armed=False, auto_brake_active=False,
                              steering_limit_deg=75., manual_brake_used=False, auto_brake_used=False)
        return {"state": self.state, "done": False, "event": "REALTIME_READY"}

    def get_state(self):
        return self.state

    def step(self, raw_action):
        action_type = GroundBrakeAction if self.brake_protocol else GroundRealtimeAction
        action = action_type.model_validate(raw_action)
        if action.nose_wheel_deg > self.parameters.target_nose_wheel_deg:
            raise ValueError("前轮指令超过本次实验的目标转角")
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
        done = (sim["complete"] or not sim["safe"] or self.sequence >= self.max_steps
                or sim["time_s"] >= self.parameters.max_simulation_time_s - 1e-8)
        phase = "SUCCESS" if sim["complete"] else "FAILED" if done else "TURN" if self.reached_5 else "ACCELERATE"
        manual_used = self.state.get("manual_brake_used", False)
        auto_used = self.state.get("auto_brake_used", False)
        self.state = {"flight_phase": phase, "time": sim["time_s"],
                      **{k: sim[k] for k in ["speed_kn", "heading_deg", "yaw_rate_deg_s", "wheel_deg", "x_m", "y_m", "roll_deg", "on_ground"]},
                      "reached_5kn": self.reached_5,
                      "target_nose_wheel_deg": self.parameters.target_nose_wheel_deg,
                      "target_heading_change_deg": self.parameters.target_heading_change_deg,
                      "max_simulation_time_s": self.parameters.max_simulation_time_s}
        applied = action.model_dump()
        if self.brake_protocol:
            self.state.update({k: sim[k] for k in ["brake_left", "brake_right", "brake_system_mode",
                               "auto_brake_armed", "auto_brake_active", "steering_limit_deg"]})
            self.state.update(manual_brake_used=bool(manual_used or (sim["brake_system_mode"] == 0
                              and max(sim["brake_left"], sim["brake_right"]) > 0)),
                              auto_brake_used=bool(auto_used or sim["auto_brake_active"]))
            applied.update(brake_left=sim["brake_left"], brake_right=sim["brake_right"])
        return {"state": self.state, "done": done, "event": phase,
                "applied_action": applied,
                "simulation": {k: v for k, v in sim.items() if k != "trajectory"},
                "simulation_file": str(self.folder / f"response_{self.sequence:03d}.json")}

    def close(self):
        (self.folder / "stop.flag").write_text("stop", encoding="utf-8")
        if self.worker is not None:
            try: self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired: self.worker.terminate()
        if self.log: self.log.close()
