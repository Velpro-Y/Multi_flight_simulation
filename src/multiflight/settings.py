"""Application and migrated 6DOF simulation settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

RESOURCE_DIR = PROJECT_ROOT / "resources"
SCENE_DIR = RESOURCE_DIR / "scenes"
PROMPT_DIR = RESOURCE_DIR / "prompts"
DIFY_DIR = RESOURCE_DIR / "dify"
SIMULINK_DIR = PROJECT_ROOT / "simulink"
DATA_DIR = PROJECT_ROOT / "data"
RUN_DIR = DATA_DIR / "runs"
LOG_DIR = DATA_DIR / "logs"
DB_FILE = DATA_DIR / "multiflight.db"
PROMPT_REGISTRY_FILE = DATA_DIR / "prompt_registry.json"

for directory in (DATA_DIR, RUN_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "http://localhost/v1").rstrip("/")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
DIFY_TIMEOUT_SECONDS = float(os.getenv("DIFY_TIMEOUT_SECONDS", "1800"))

# Simulink
MODEL_NAME = "beaver_agent_env"
MODEL_FILE = SIMULINK_DIR / "beaver_agent_env.slx"
STATE_FILE = SIMULINK_DIR / "beaver_state.mat"
# Dify Agent currently allows at most 99 iterations. A two-second simulation
# interval keeps the complete 500 -> 300 -> 200 -> 500 ft experiment within
# that limit while preserving event-triggered phase transitions.
STEP_TIME = 2.0

# Unit conversion: Simulink remains SI; the Python API uses ft and ft/s.
M_TO_FT = 3.280839895013123
MPS_TO_FPS = M_TO_FT

# Scenario phases and thresholds.
PHASE_TWIN_DESCENT = "TWIN_DESCENT"
PHASE_ENGINE_OUT_DESCENT = "ENGINE_OUT_DESCENT"
PHASE_GO_AROUND = "GO_AROUND"
PHASE_SUCCESS = "SUCCESS"

ENGINE_FAILURE_ALTITUDE_FT = 300.0
GO_AROUND_ALTITUDE_FT = 200.0
TARGET_ALTITUDE_FT = 500.0
GO_AROUND_TRANSITION_TIME_S = 6.0

TWIN_DESCENT_TRIM = {
    "vertical_speed": -9.842519685039,
    "airspeed": 148.911745406824,
    "roll": 0.0136160413039,
    "pitch": 0.0647610681203,
    "aileron": 0.00202547955338,
    "elevator": -0.0109658218634,
    "rudder": -0.0374364069557,
    "throttle_left": 0.16863024396,
    "throttle_right": 0.16863024396,
}

ENGINE_OUT_DESCENT_TRIM = {
    "vertical_speed": -9.842519685039,
    "airspeed": 148.911745406824,
    "roll": 0.0175700775848,
    "pitch": 0.0647598704702,
    "aileron": 0.000818445603132,
    "elevator": -0.0109595158183,
    "rudder": -0.0520614487636,
    "throttle_left": 0.0,
    "throttle_right": 0.207220892838,
}

ENGINE_OUT_CLIMB_TRIM = {
    "vertical_speed": 4.921259842520,
    "airspeed": 148.950131233596,
    "roll": 0.0848432053851,
    "pitch": 0.162303204528,
    "aileron": -0.019551264426,
    "elevator": -0.00965061067912,
    "rudder": -0.299092570837,
    "throttle_left": 0.0,
    "throttle_right": 0.614702877432,
}

DEFAULT_STATE = {"AltitudeMSL": TARGET_ALTITUDE_FT}

ACTION_LIMIT = {
    "aileron": (-1.0, 1.0),
    "elevator": (-1.0, 1.0),
    "rudder": (-1.0, 1.0),
    "throttle": (0.0, 1.0),
}

