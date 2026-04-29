from .payloads import ProfitContributionPayload

class ProfitContributionRenderer:
    def __init__(self, payload: ProfitContributionPayload):
        self.payload = payload

    def render(self) -> str:
        """Render profit contribution table.
        Numbers are formatted with thousands separator and one decimal for percentages.
        Example line: "Product A | 120,000 | 40.0%"
        """
        lines = []
        for item in self.payload.items:
            profit_str = f"{item.profit:,.0f}".replace(',', ',')
            # format percentage with one decimal place
            perc = item.contribution * 100
            perc_str = f"{perc:.1f}%"
            lines.append(f"{item.name} | {profit_str} | {perc_str}")
        return "\n".join(lines)
