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


if __name__ == "__main__":
    unittest.main()

