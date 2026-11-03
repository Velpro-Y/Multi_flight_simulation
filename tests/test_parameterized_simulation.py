from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from multiflight.db import JobStore
from multiflight.main import get_scene_parameters
from multiflight.prompts import PromptCompiler
from multiflight.scene_registry import SceneRegistry
from multiflight.schemas import EngineFailureParameters
from multiflight.services.preparation_service import (
    PreparationError,
    PreparationService,
)
from multiflight.simulation.flight_env import FlightEnv


class FakeTrimProvider:
    def prepare_engine_failure(self, parameters: dict) -> dict:
        airspeed = parameters["initial_airspeed_ft_s"]
        state = {
            "phi": 0.01,
            "theta": 0.06,
            "psi": 0.0,
            "p": 0.0,
            "q": 0.0,
            "r": 0.0,
            "U": airspeed * 0.3048,
            "V": 0.0,
            "W": 5.0,
            "XN": 0.0,
            "YE": 0.0,
            "ZD": -parameters["initial_altitude_ft"] * 0.3048,
        }
        def profile(engine_out: bool, climb: bool = False) -> dict:
            return {
                "vertical_speed": 4.92 if climb else -9.84,
                "airspeed": airspeed,
                "roll": 0.08 if climb else 0.01,
                "pitch": 0.16 if climb else 0.06,
                "aileron": -0.02 if climb else 0.002,
                "elevator": -0.01,
                "rudder": -0.29 if climb else -0.04,
                "throttle_left": 0.0 if engine_out else 0.17,
                "throttle_right": 0.62 if climb else 0.21,
                "state": state,
            }

        return {
            "converged": True,
            "solver": "fake",
            "model_version": "test",
            "message": "ok",
            "initial_state": state,
            "profiles": {
                "twin_descent": profile(False),
                "engine_out_descent": profile(True),
                "engine_out_climb": profile(True, True),
            },
        }


class FakeMatlabEngine:
    def __init__(self) -> None:
        self.workspace = {}
        self.expressions: list[str] = []

    def eval(self, expression: str, nargout: int = 0):
        self.expressions.append(expression)
        if "exist('simOut', 'var')" in expression:
            return 0
        return None


@pytest.fixture
def test_db_path() -> Path:
    path = Path("data") / f"test-preparation-{uuid.uuid4().hex}.db"
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


def _service(db_path: Path) -> PreparationService:
    return PreparationService(
        jobs=JobStore(db_path),
        scenes=SceneRegistry(),
        trimmer=FakeTrimProvider(),
        execution_lock=threading.Lock(),
    )


def test_frontend_schema_exposes_supported_and_reserved_fields() -> None:
    schema = get_scene_parameters("engine_failure")
    fields = {
        field["name"]: field
        for group in schema["groups"]
        for field in group["fields"]
    }
    assert schema["runnable"] is True
    assert fields["initial_altitude_ft"]["capability"] == "supported"
    assert fields["wind_speed_ft_s"]["capability"] == "reserved"


def test_invalid_altitude_order_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EngineFailureParameters(
            initial_altitude_ft=500,
            engine_failure_altitude_ft=250,
            go_around_altitude_ft=300,
        )


def test_preparation_is_stored_and_reusable(test_db_path: Path) -> None:
    service = _service(test_db_path)
    parameters = EngineFailureParameters(
        initial_altitude_ft=600,
        initial_airspeed_ft_s=150,
        engine_failure_altitude_ft=350,
        go_around_altitude_ft=220,
        target_altitude_ft=600,
    )
    result = service.prepare("engine_failure", parameters)
    loaded = service.get_ready(result["preparation_id"], "engine_failure")
    assert result["status"] == "ready"
    assert result["trim"]["converged"] is True
    assert loaded["normalized_parameters"]["initial_altitude_ft"] == 600


def test_nonzero_wind_is_not_silently_ignored(test_db_path: Path) -> None:
    service = _service(test_db_path)
    with pytest.raises(PreparationError) as caught:
        service.prepare(
            "engine_failure", EngineFailureParameters(wind_speed_ft_s=5.0)
        )
    assert caught.value.code == "CAPABILITY_NOT_AVAILABLE"


def test_prompt_uses_runtime_parameters_and_trim() -> None:
    scene = SceneRegistry().get("engine_failure")
    service_context = {
        "normalized_parameters": EngineFailureParameters(
            initial_altitude_ft=600,
            engine_failure_altitude_ft=350,
            go_around_altitude_ft=220,
            target_altitude_ft=600,
        ).model_dump(),
        "trim": FakeTrimProvider().prepare_engine_failure(
            EngineFailureParameters(initial_altitude_ft=600).model_dump()
        ),
    }
    artifact = PromptCompiler().compile(
        scene, "test", runtime_context=service_context
    )
    assert "350.0 ft 左发动机失效" in artifact.text
    assert "复飞高度：220.0 ft" in artifact.text
    assert "runtime_parameters" in artifact.block_hashes


def test_flight_environment_uses_prepared_initial_state(monkeypatch) -> None:
    parameters = EngineFailureParameters(
        initial_altitude_ft=600,
        initial_airspeed_ft_s=150,
        engine_failure_altitude_ft=350,
        go_around_altitude_ft=220,
        target_altitude_ft=600,
    )
    trim = FakeTrimProvider().prepare_engine_failure(parameters.model_dump())
    monkeypatch.setattr(
        "multiflight.simulation.flight_env.get_engine", lambda: FakeMatlabEngine()
    )
    run_id = f"test-{uuid.uuid4().hex}"
    environment = FlightEnv(
        run_id=run_id,
        configuration={
            "normalized_parameters": parameters.model_dump(),
            "trim": trim,
        },
    )
    try:
        reset = environment.reset()
        assert reset["state"]["altitude"] == 600
        assert reset["state"]["airspeed"] == 150
        assert "350.0 ft" in reset["instruction"]
        assert environment.go_around_altitude == 220
        assert environment.target_altitude == 600
    finally:
        if environment.log_file.exists():
            environment.log_file.unlink()


def test_parameterized_first_step_sets_each_6dof_parameter_separately(
    monkeypatch,
) -> None:
    parameters = EngineFailureParameters(
        initial_altitude_ft=600,
        initial_airspeed_ft_s=150,
        engine_failure_altitude_ft=350,
        go_around_altitude_ft=220,
        target_altitude_ft=600,
    )
    trim = FakeTrimProvider().prepare_engine_failure(parameters.model_dump())
    engine = FakeMatlabEngine()
    monkeypatch.setattr(
        "multiflight.simulation.flight_env.get_engine", lambda: engine
    )
    run_id = f"test-{uuid.uuid4().hex}"
    environment = FlightEnv(
        run_id=run_id,
        configuration={
            "normalized_parameters": parameters.model_dump(),
            "trim": trim,
        },
    )
    try:
        environment.reset()
        environment.get_state = lambda: {
            "status": "running",
            "time": 2.0,
            "altitude": 580.0,
            "airspeed": 150.0,
            "vertical_speed": -9.84,
            "roll": 0.01,
            "pitch": 0.06,
            "yaw": 0.0,
            "roll_rate": 0.0,
            "pitch_rate": 0.0,
            "yaw_rate": 0.0,
            "left_engine_fail": False,
            "flight_phase": "TWIN_DESCENT",
        }
        environment.step(
            {
                "aileron": 0.002,
                "elevator": -0.01,
                "rudder": -0.04,
                "throttle_left": 0.17,
                "throttle_right": 0.17,
            }
        )
        command = next(
            expression
            for expression in engine.expressions
            if "setBlockParameter" in expression
        )
        assert command.count("setBlockParameter") == 4
        for parameter_name in ("xme_0", "Vm_0", "eul_0", "pm_0"):
            assert f"'{parameter_name}'" in command
    finally:
        if environment.log_file.exists():
            environment.log_file.unlink()
