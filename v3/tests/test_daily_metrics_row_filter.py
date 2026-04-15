import unittest

from v3.pipeline.daily_metrics_stage import _filter_rows_by_day


class TestDailyMetricsRowFilter(unittest.TestCase):
    def test_rows_are_filtered_by_exact_day(self) -> None:
        rows = [
            {"id": "a", "date": "2026-04-14T10:00:00"},
            {"id": "b", "orderDate": "2026-04-14 23:59:59"},
            {"id": "c", "saleDate": "2026-04-15"},
            {"id": "d", "date": "2026-04-13T02:00:00"},
            {"id": "e", "date": ""},
            {"id": "f"},
        ]

        filtered = _filter_rows_by_day(rows, "2026-04-14")
        kept_ids = [str(row.get("id") or "") for row in filtered if isinstance(row, dict)]
        self.assertEqual(kept_ids, ["a", "b"])

    def test_rows_keep_only_target_day_across_supported_keys(self) -> None:
        rows = [
            {"id": "x1", "date": "2026-04-14"},
            {"id": "x2", "orderDate": "2026-04-14T03:00:00"},
            {"id": "x3", "saleDate": "2026-04-14 18:30:00"},
            {"id": "x4", "date": "2026-04-13"},
            {"id": "x5", "orderDate": "2026-04-15"},
            {"id": "x6", "saleDate": "2026-04-16"},
        ]

        filtered = _filter_rows_by_day(rows, "2026-04-14")
        kept_ids = [str(row.get("id") or "") for row in filtered if isinstance(row, dict)]
        self.assertEqual(kept_ids, ["x1", "x2", "x3"])


if __name__ == "__main__":
    unittest.main()
