import unittest

from v3.outputs.daily_report_stage import (
    _assert_sku_status_counts_match,
    _sku_status_counts_from_health_rows,
)


class TestDailyReportSkuStatusCounts(unittest.TestCase):
    def test_counts_are_built_from_same_health_dataset(self) -> None:
        rows = [
            {"sku": "A", "status": "Рост"},
            {"sku": "B", "status": "Нормально"},
            {"sku": "C", "status": "Риск"},
            {"sku": "D", "status": "Ликвидация"},
            {"sku": "E", "status": "healthy"},
            {"sku": "F", "status": "unstable"},
        ]
        counts = _sku_status_counts_from_health_rows(rows)
        self.assertEqual(
            counts,
            {
                "growth": 1,
                "normal": 2,
                "risk": 2,
                "liquidation": 1,
            },
        )

    def test_assertion_detects_mismatch(self) -> None:
        rows = [
            {"sku": "A", "status": "Рост"},
            {"sku": "B", "status": "Риск"},
        ]
        summary_counts = {
            "growth": 1,
            "normal": 1,
            "risk": 0,
            "liquidation": 0,
        }
        with self.assertRaises(AssertionError):
            _assert_sku_status_counts_match(summary_counts, rows)


if __name__ == "__main__":
    unittest.main()
