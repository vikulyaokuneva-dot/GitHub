import json
from pathlib import Path
from typing import Any

from research_engine.domain.models import ResearchInput


class ResearchInputValidationError(ValueError):
    """Raised when scenario config cannot be converted into a valid ResearchInput."""


class ResearchInputLoader:
    ALLOWED_COMPETITION_LEVELS = {"low", "medium", "high"}

    def load(self, scenario_path: Path) -> ResearchInput:
        path = Path(scenario_path)
        if not path.exists():
            raise ResearchInputValidationError(f"Scenario config was not found: {path}")

        try:
            raw_data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ResearchInputValidationError(f"Scenario config is not valid JSON: {path}") from exc

        return self.from_dict(raw_data)

    def from_dict(self, payload: dict[str, Any]) -> ResearchInput:
        if not isinstance(payload, dict):
            raise ResearchInputValidationError("Scenario config must be a JSON object.")

        input_data = ResearchInput(
            scenario_name=self._require_non_empty_string(payload, "scenario_name"),
            budget_total=self._require_float(payload, "budget_total"),
            target_price_min=self._require_float(payload, "target_price_min"),
            target_price_max=self._require_float(payload, "target_price_max"),
            target_margin_pct=self._require_float(payload, "target_margin_pct"),
            preferred_categories=self._require_string_list(payload, "preferred_categories"),
            excluded_categories=self._require_string_list(payload, "excluded_categories"),
            max_competition_level=self._require_non_empty_string(payload, "max_competition_level"),
            notes=self._optional_string(payload, "notes"),
        )
        self.validate(input_data)
        return input_data

    def validate(self, input_data: ResearchInput) -> None:
        if not input_data.scenario_name.strip():
            raise ResearchInputValidationError("scenario_name must not be empty.")
        if input_data.budget_total <= 0:
            raise ResearchInputValidationError("budget_total must be greater than 0.")
        if input_data.target_price_min <= 0:
            raise ResearchInputValidationError("target_price_min must be greater than 0.")
        if input_data.target_price_max < input_data.target_price_min:
            raise ResearchInputValidationError("target_price_max must be >= target_price_min.")
        if input_data.target_margin_pct < 0:
            raise ResearchInputValidationError("target_margin_pct must be >= 0.")
        if not isinstance(input_data.preferred_categories, list):
            raise ResearchInputValidationError("preferred_categories must be a list.")
        if not isinstance(input_data.excluded_categories, list):
            raise ResearchInputValidationError("excluded_categories must be a list.")
        level = input_data.max_competition_level.lower()
        if level not in self.ALLOWED_COMPETITION_LEVELS:
            allowed = ", ".join(sorted(self.ALLOWED_COMPETITION_LEVELS))
            raise ResearchInputValidationError(
                f"max_competition_level must be one of: {allowed}. Received: {input_data.max_competition_level}"
            )

    def _require_float(self, payload: dict[str, Any], key: str) -> float:
        if key not in payload:
            raise ResearchInputValidationError(f"Missing required field: {key}")
        try:
            return float(payload[key])
        except (TypeError, ValueError) as exc:
            raise ResearchInputValidationError(f"Field '{key}' must be numeric.") from exc

    def _require_non_empty_string(self, payload: dict[str, Any], key: str) -> str:
        if key not in payload:
            raise ResearchInputValidationError(f"Missing required field: {key}")
        value = payload[key]
        if not isinstance(value, str):
            raise ResearchInputValidationError(f"Field '{key}' must be a string.")
        if not value.strip():
            raise ResearchInputValidationError(f"Field '{key}' must not be empty.")
        return value.strip()

    def _require_string_list(self, payload: dict[str, Any], key: str) -> list[str]:
        if key not in payload:
            raise ResearchInputValidationError(f"Missing required field: {key}")
        value = payload[key]
        if not isinstance(value, list):
            raise ResearchInputValidationError(f"Field '{key}' must be a list.")
        if not all(isinstance(item, str) for item in value):
            raise ResearchInputValidationError(f"Field '{key}' must contain only strings.")
        return value

    def _optional_string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ResearchInputValidationError(f"Field '{key}' must be a string.")
        return value
