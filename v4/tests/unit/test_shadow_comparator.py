from __future__ import annotations

import unittest

from v4.shadow.comparator import compare_results


def _result_payload(
    *,
    revenue: float | None,
    profit: float | None,
    margin: float | None,
    stock_units: int | None,
    out_of_stock: int | None,
    decision_counts: dict[str, int],
    decision_codes: list[str],
    partial_flag: bool,
    warnings_count: int,
) -> dict:
    return {
        "outputs": {
            "artifacts": {
                "payloads": {
                    "facts": {
                        "sections": {
                            "financial": {
                                "items": [
                                    {"key": "revenue_gross", "value": {"value": revenue}},
                                    {"key": "net_profit_like", "value": {"value": profit}},
                                    {"key": "margin", "value": {"value": margin}},
                                ]
                            },
                            "stock": {
                                "items": [
                                    {"key": "total_stock_units", "value": {"value": stock_units}},
                                    {"key": "out_of_stock_items_count", "value": {"value": out_of_stock}},
                                ]
                            },
                        }
                    },
                    "decisions": {
                        "summary": {
                            "by_priority": decision_counts,
                            "decision_codes": decision_codes,
                        }
                    },
                    "outputs_summary": {
                        "partial_flag": partial_flag,
                        "warnings_count": warnings_count,
                    },
                }
            }
        }
    }


class TestShadowComparator(unittest.TestCase):
    def test_comparator_detects_differences(self) -> None:
        v4_result = _result_payload(
            revenue=1000.0,
            profit=100.0,
            margin=10.0,
            stock_units=50,
            out_of_stock=2,
            decision_counts={"P1": 1, "P2": 0, "P3": 0},
            decision_codes=["negative_profit"],
            partial_flag=False,
            warnings_count=3,
        )
        legacy_result = _result_payload(
            revenue=700.0,
            profit=20.0,
            margin=5.0,
            stock_units=40,
            out_of_stock=1,
            decision_counts={"P1": 0, "P2": 1, "P3": 0},
            decision_codes=["low_margin"],
            partial_flag=False,
            warnings_count=1,
        )

        comparison = compare_results(v4_result, legacy_result)
        self.assertIn("differences", comparison)
        self.assertTrue(len(comparison["differences"]) > 0)
        self.assertIn(comparison["severity"], {"low", "medium", "high"})

    def test_partial_context_is_tolerant(self) -> None:
        v4_result = _result_payload(
            revenue=None,
            profit=None,
            margin=None,
            stock_units=10,
            out_of_stock=None,
            decision_counts={"P1": 0, "P2": 0, "P3": 0},
            decision_codes=[],
            partial_flag=True,
            warnings_count=5,
        )
        legacy_result = _result_payload(
            revenue=1000.0,
            profit=100.0,
            margin=10.0,
            stock_units=10,
            out_of_stock=0,
            decision_counts={"P1": 0, "P2": 0, "P3": 0},
            decision_codes=[],
            partial_flag=True,
            warnings_count=4,
        )

        comparison = compare_results(v4_result, legacy_result)
        self.assertIn("partial context", " ".join(comparison["notes"]))
        self.assertNotEqual(comparison["severity"], "high")


if __name__ == "__main__":
    unittest.main()

