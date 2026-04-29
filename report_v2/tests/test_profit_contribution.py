import pytest
from report_v2.payload import ProfitContributionPayload
from report_v2.renderer import ProfitContributionRenderer

@pytest.fixture
def sample_data():
    return {
        "profit": 120000,
        "cost": 80000,
        "margin": 0.4,
        "details": [
            {"sku": "SKU123", "profit": 5000, "cost": 3000},
            {"sku": "SKU124", "profit": 7000, "cost": 4000},
        ],
    }

def test_profit_contribution_payload(sample_data):
    payload = ProfitContributionPayload(sample_data)
    assert payload.profit == 120000
    assert payload.cost == 80000
    assert payload.margin == pytest.approx(0.4)
    assert len(payload.details) == 2
    assert payload.details[0]["sku"] == "SKU123"

def test_profit_contribution_renderer(sample_data):
    payload = ProfitContributionPayload(sample_data)
    renderer = ProfitContributionRenderer(payload)
    output = renderer.render()
    # Ensure key sections are present
    assert "Profit Contribution" in output
    assert "Total Profit" in output
    assert "SKU123" in output
    assert "SKU124" in output
    # Verify calculated values appear correctly
    assert "120,000" in output  # formatted profit
    assert "80,000" in output   # formatted cost
    assert "40.0%" in output   # formatted margin
