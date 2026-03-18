from __future__ import annotations

import unittest

from v4.core.contracts import MetricStatus, MetricValue


class TestMetricValueContracts(unittest.TestCase):
    def test_none_value_is_preserved(self) -> None:
        metric = MetricValue(
            value=None,
            status=MetricStatus.UNAVAILABLE.value,
            source="realization",
            note="missing source",
        )
        self.assertIsNone(metric.value)
        self.assertEqual(metric.status, "unavailable")
        self.assertNotEqual(metric.value, 0)

    def test_unavailable_metric_not_converted_to_zero(self) -> None:
        metric = MetricValue(
            value=None,
            status=MetricStatus.UNAVAILABLE.value,
            source=None,
            note=None,
        )
        self.assertIsNone(metric.value)
        self.assertEqual(metric.status, MetricStatus.UNAVAILABLE.value)


if __name__ == "__main__":
    unittest.main()
