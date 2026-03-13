import unittest

from v3.outputs.daily_artifacts_stage import prepare_daily_output_payload


class TestDailyOutputKeywordPayload(unittest.TestCase):
    def test_reads_keyword_monitoring_from_analytics_when_payload_missing(self) -> None:
        payload = prepare_daily_output_payload(
            {
                "out_dir": "",
                "analytics": {
                    "keyword_monitoring": {
                        "status": "ok",
                        "summary": {
                            "sku_count_with_keywords": 1,
                            "total_query_count": 2,
                            "winner_query_count": 1,
                        },
                        "sku_items": [
                            {
                                "sku": "SKU1",
                                "query_count": 2,
                                "winner_queries_count": 1,
                                "keyword_health_status": "healthy",
                            }
                        ],
                    }
                },
            }
        )

        keyword_payload = payload.get("keyword_monitoring", {})
        self.assertIsInstance(keyword_payload, dict)
        self.assertEqual(keyword_payload.get("status"), "ok")
        self.assertEqual(payload.get("keyword_summary", {}).get("sku_count_with_keywords"), 1)


if __name__ == "__main__":
    unittest.main()
