import json
from typing import Any, Dict

# Existing renderer definitions ...

# --- Added ProfitContributionRenderer ---

class ProfitContributionRenderer:
    """Renderer for ProfitContributionPayload.

    Provides a ``render`` method that returns JSON representation of the payload.
    """

    def __init__(self, payload: Any):
        # Accept any object that implements ``to_dict``
        if not hasattr(payload, "to_dict"):
            raise TypeError("Payload must implement to_dict method")
        self.payload = payload

    def render(self) -> str:
        """Render the payload to a JSON string.

        Returns:
            A JSON-formatted string of the payload dictionary.
        """
        payload_dict: Dict[str, Any] = self.payload.to_dict()
        return json.dumps(payload_dict, ensure_ascii=False)

# Update __all__ if present.
try:
    __all__.append('ProfitContributionRenderer')
except NameError:
    __all__ = ['ProfitContributionRenderer']
