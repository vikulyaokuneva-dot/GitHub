"""Small environment configuration surface for application shells."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret settings only; credentials will use encrypted storage later."""

    service_name: str
    environment: str
    version: str

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            service_name=os.getenv("WB_AUTOPILOT_SERVICE_NAME", "wb-autopilot-api"),
            environment=os.getenv("WB_AUTOPILOT_ENVIRONMENT", "development"),
            version=os.getenv("WB_AUTOPILOT_VERSION", "0.1.0"),
        )
