import unittest

from v3.outputs.daily_artifacts_stage import prepare_daily_output_payload


class TestDailyOutputProfitPayload(unittest.TestCase):
    def test_reads_profit_contribution_from_analytics_when_payload_missing(self) -> None:
        payload = prepare_daily_output_payload(
            {
                "out_dir": "",
                "analytics": {
                    "profit_contribution": {
                        "status": "ok",
                        "summary": {"sku_count": 1},
                        "items": [{"sku": "SKU1", "profit": 10.0, "profit_group": "P1"}],
                    }
                },
            }
        )
        pc = payload.get("profit_contribution", {})
        self.assertIsInstance(pc, dict)
        self.assertEqual(pc.get("status"), "ok")
        self.assertEqual(len(pc.get("items", [])), 1)
        self.assertEqual(payload.get("analytics", {}).get("profit_contribution", {}).get("summary", {}).get("sku_count"), 1)


if __name__ == "__main__":
    unittest.main()
