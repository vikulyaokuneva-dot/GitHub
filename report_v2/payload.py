from dataclasses import dataclass
from typing import List, Dict, Any

# Existing payload definitions ...

# --- Added ProfitContributionPayload ---

@dataclass
class ProfitContributionPayload:
    """Payload for profit contribution report.

    Attributes:
        data: List of dictionaries representing rows of the report.
    """
    data: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert payload to a serializable dictionary.

        Returns:
            dict with a single key ``'profit_contribution'`` containing the data.
        """
        return {"profit_contribution": self.data}

# Ensure __all__ includes the new class if the module defines it.
try:
    __all__.append('ProfitContributionPayload')
except NameError:
    __all__ = ['ProfitContributionPayload']
