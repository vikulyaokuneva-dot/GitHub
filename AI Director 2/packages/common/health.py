"""Typed health and readiness contracts."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class HealthState(StrEnum):
    """Operational state used by liveness and readiness endpoints."""

    OK = "ok"
    NOT_READY = "not_ready"
    DEGRADED = "degraded"


class ComponentHealth(BaseModel):
    """Health of one required dependency."""

    name: str = Field(min_length=1, max_length=100)
    state: HealthState
    detail: str | None = Field(default=None, max_length=500)


class HealthPayload(BaseModel):
    """Public operational response. It never includes credentials or URLs."""

    service: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)
    state: HealthState
    components: list[ComponentHealth]
    detail: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def reject_ready_payload_with_unready_component(self) -> HealthPayload:
        if self.state == HealthState.OK and any(component.state != HealthState.OK for component in self.components):
            raise ValueError("overall health cannot be ok when a component is not ok")
        return self

    @property
    def is_ready(self) -> bool:
        return self.state == HealthState.OK and all(component.state == HealthState.OK for component in self.components)


ReadinessProbe = Callable[[], HealthPayload]


class StaticReadinessProbe:
    """Factory for explicit readiness states before concrete probes exist."""

    @staticmethod
    def not_configured() -> ReadinessProbe:
        def probe() -> HealthPayload:
            return HealthPayload(
                service="wb-autopilot-api",
                environment="unknown",
                state=HealthState.NOT_READY,
                components=[
                    ComponentHealth(
                        name="infrastructure",
                        state=HealthState.NOT_READY,
                        detail="PostgreSQL, Redis and RabbitMQ probes are not configured yet.",
                    )
                ],
            )

        return probe
