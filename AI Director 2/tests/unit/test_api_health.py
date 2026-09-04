from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.common.health import ComponentHealth, HealthPayload, HealthState
from packages.common.settings import Settings


def _settings() -> Settings:
    return Settings(service_name="test-api", environment="test", version="0.1.0-test")


def test_healthz_is_alive_without_infrastructure() -> None:
    client = TestClient(create_app(settings=_settings()))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "service": "test-api",
        "environment": "test",
        "state": "ok",
        "components": [],
        "detail": None,
    }


def test_readyz_is_unavailable_until_dependencies_are_configured() -> None:
    client = TestClient(create_app(settings=_settings()))

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["state"] == "not_ready"
    assert response.json()["components"][0]["name"] == "infrastructure"


def test_readyz_returns_success_when_injected_probe_confirms_dependencies() -> None:
    def ready_probe() -> HealthPayload:
        return HealthPayload(
            service="test-api",
            environment="test",
            state=HealthState.OK,
            components=[ComponentHealth(name="postgres", state=HealthState.OK)],
        )

    client = TestClient(create_app(settings=_settings(), readiness_probe=ready_probe))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["state"] == "ok"
