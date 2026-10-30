from __future__ import annotations

import pytest
from fastapi import HTTPException

from multiflight.main import get_compiled_prompt, health, list_scenarios, start_run
from multiflight.schemas import RunRequest


def test_health_does_not_require_matlab_connection() -> None:
    response = health()
    assert response["status"] == "ok"
    assert response["simulation"]["ready"] is False


def test_scene_and_compiled_prompt_endpoints() -> None:
    scenes = list_scenarios()
    assert len(scenes) == 3

    prompt = get_compiled_prompt("engine_failure")
    assert prompt["version"] == "1.0.0"
    assert "单发失效复飞" in prompt["text"]


def test_reserved_scene_cannot_start() -> None:
    with pytest.raises(HTTPException) as caught:
        start_run(RunRequest(scene_id="ground_deceleration"))
    assert caught.value.status_code == 409
