import pytest
from pydantic import ValidationError

from multiflight.services.ground_demo import GroundDemoRequest, parse_decision


def test_decision_and_boundaries():
    assert parse_decision('```json\n{"nose_wheel_deg":-10}\n```').nose_wheel_deg == -10
    with pytest.raises(ValidationError):
        parse_decision('{"nose_wheel_deg":40}')
    with pytest.raises(ValidationError):
        GroundDemoRequest(initial_speed_kn=30)
    assert GroundDemoRequest().nose_wheel_deg is None


def test_demo_endpoint(monkeypatch):
    from multiflight.main import app, ground_demo_service, start_ground_demo

    monkeypatch.setattr(ground_demo_service, "start", lambda request: {
        "id": "ground-test", "direction": request.direction,
        "nose_wheel_deg": request.nose_wheel_deg,
    })
    response = start_ground_demo(GroundDemoRequest(direction="left"))
    assert response["nose_wheel_deg"] is None
    assert "202" in app.openapi()["paths"]["/api/ground-direction/demo"]["post"]["responses"]


def test_differential_throttle_bounds():
    assert GroundDemoRequest(maneuver="uturn", differential_throttle=0.1).differential_throttle == 0.1
    with pytest.raises(ValidationError):
        GroundDemoRequest(differential_throttle=0.1)
    with pytest.raises(ValidationError):
        GroundDemoRequest(maneuver="uturn", differential_throttle=0.2)


def test_inner_idle_policy():
    assert GroundDemoRequest(maneuver="uturn", thrust_policy="inner_idle").differential_throttle == 0
    with pytest.raises(ValidationError):
        GroundDemoRequest(thrust_policy="inner_idle")
    with pytest.raises(ValidationError):
        GroundDemoRequest(maneuver="uturn", thrust_policy="inner_idle", differential_throttle=0.1)
