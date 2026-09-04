"""Worker entry point before Celery jobs are introduced."""

from __future__ import annotations

import json

from packages.common.health import HealthPayload, HealthState
from packages.common.settings import Settings


def worker_health(settings: Settings | None = None) -> HealthPayload:
    """Return an explicit shell status without claiming job-processing ability."""

    resolved_settings = settings or Settings.from_environment()
    return HealthPayload(
        service="wb-autopilot-worker",
        environment=resolved_settings.environment,
        state=HealthState.NOT_READY,
        components=[],
        detail="Worker shell is present; task queue integration is not configured yet.",
    )


def main() -> None:
    """Expose shell state for local diagnostics until the Celery app exists."""

    print(json.dumps(worker_health().model_dump(mode="json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
