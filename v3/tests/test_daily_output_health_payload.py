import unittest

from v3.outputs.daily_artifacts_stage import prepare_daily_output_payload


class TestDailyOutputHealthPayload(unittest.TestCase):
    def test_reads_health_from_analytics_when_health_payload_missing(self) -> None:
        payload = prepare_daily_output_payload(
            {
                "out_dir": "",
                "analytics": {
                    "health_score": {
                        "status": "ok",
                        "items": [{"sku": "SKU1", "health_score": 7.5, "health_status": "healthy"}],
                        "summary": {"status": "ok", "sku_count": 1, "scored_sku_count": 1},
                    }
                },
            }
        )
        health_payload = payload.get("health_payload", {})
        self.assertIsInstance(health_payload, dict)
        self.assertEqual(health_payload.get("status"), "ok")
        self.assertEqual(len(health_payload.get("items", [])), 1)
        self.assertEqual(payload.get("health_summary", {}).get("sku_count"), 1)


if __name__ == "__main__":
    unittest.main()
