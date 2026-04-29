from dataclasses import dataclass
from typing import List

@dataclass
class ProfitContributionItem:
    name: str
    profit: float
    contribution: float  # percentage as float, e.g., 0.4 for 40%

@dataclass
class ProfitContributionPayload:
    items: List[ProfitContributionItem]

    @classmethod
    def from_raw(cls, raw_data: List[dict]):
        """Create payload from raw list of dicts with keys 'name', 'profit', 'contribution'.
        The 'contribution' value is expected as a percentage number (e.g., 40.0 for 40%).
        """
        items = []
        for entry in raw_data:
            # Ensure proper types and fallback defaults
            name = entry.get('name', '')
            profit = float(entry.get('profit', 0))
            contribution = float(entry.get('contribution', 0)) / 100.0  # store as fraction
            items.append(ProfitContributionItem(name=name, profit=profit, contribution=contribution))
        return cls(items=items)
