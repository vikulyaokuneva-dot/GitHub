import unittest

from v3.outputs.email_sender_orchestrator import build_daily_email_body


class TestEmailBodyRussianClean(unittest.TestCase):
    def test_body_is_russian_and_filters_mojibake_raw_fields(self) -> None:
        summary = {
            "financial_finality_status": "partial",
            "ai_guidance_mode": "preliminary",
            "ai_guardrail_reasons": ["financial contour is not final", "РќРµРєРѕСЂСЂРµРєС‚РЅРѕ"],
            "orders_count_confirmed": False,
            "display": {
                "orders_count": "нет данных",
                "buyouts_count": "нет данных",
                "orders_amount": "нет данных",
                "buyouts_amount": "нет данных",
                "avg_check": "нет данных",
                "financial_revenue": "нет данных",
                "net_profit": "нет данных",
                "margin_pct": "недостаточно данных для расчета",
                "profitability_pct": "недостаточно данных для расчета",
            },
            "funnel_snapshot": {
                "funnel": {
                    "view_to_order_conversion": None,
                    "cart_to_order": None,
                    "buyout_rate": None,
                },
                "status": {
                    "traffic": "unknown",
                    "conversion": "not_confirmed",
                    "buyout_stage": "partial",
                },
            },
            "sku_watchlists": {
                "watchlists": {
                    "top_growth": [{"sku": "12345", "attention_score": 80}],
                }
            },
            "key_insights": [
                "РќРёР·РєРёР№ С‚СЂР°С„РёРє",
                "Данные по заказам пока не подтверждены",
            ],
            "recommendations": [
                "Hypothesis: keep monitoring",
                "Перепроверить данные в следующем цикле",
            ],
            "ai_day_conclusion": "РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ conclusion",
        }

        body = build_daily_email_body(
            seller_id="seller_001",
            run_date="2026-03-15",
            email_summary=summary,
            build_body=lambda _s, _d, _m: "",
        )

        self.assertIn("КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ", body)
        self.assertIn("ФИНАНСОВЫЕ ПОКАЗАТЕЛИ", body)
        self.assertIn("ГЛАВНЫЕ ВЫВОДЫ", body)
        self.assertIn("РЕКОМЕНДАЦИИ", body)
        self.assertIn("ВЫВОД ДНЯ", body)
        self.assertIn("Маржа: недостаточно данных для расчета", body)
        self.assertIn("Конверсия просмотр → заказ: недостаточно данных", body)
        self.assertIn("Данные по заказам пока не подтверждены", body)
        self.assertNotIn("COMMERCE KPI", body)
        self.assertNotIn("FINANCIAL KPI", body)
        self.assertNotIn("AI Conclusion", body)
        self.assertNotIn("РЕЖИМ РЕКОМЕНДАЦИЙ ИИ", body)
        self.assertNotIn("МОНИТОРИНГ ТОВАРОВ", body)
        self.assertNotIn("РќР", body)
        self.assertNotIn("в†", body)



    def test_order_to_buyout_over_100_is_marked_as_lag(self) -> None:
        summary = {
            "display": {
                "orders_count": "6",
                "buyouts_count": "7",
            },
            "funnel_snapshot": {
                "funnel": {
                    "view_to_order_conversion": None,
                    "buyout_rate": 116.7,
                }
            },
            "key_insights": ["\u0422\u0435\u0441\u0442"],
            "recommendations": ["\u0422\u0435\u0441\u0442"],
            "ai_day_conclusion": "\u0422\u0435\u0441\u0442",
        }

        body = build_daily_email_body(
            seller_id="seller_001",
            run_date="2026-03-16",
            email_summary=summary,
            build_body=lambda _s, _d, _m: "",
        )

        self.assertIn(
            "\u041a\u043e\u043d\u0432\u0435\u0440\u0441\u0438\u044f \u0437\u0430\u043a\u0430\u0437 \u2192 \u0432\u044b\u043a\u0443\u043f: "
            "\u043d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0434\u0430\u043d\u043d\u044b\u0445 "
            "(\u0432\u043e\u0437\u043c\u043e\u0436\u0435\u043d \u043b\u0430\u0433 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u0432\u044b\u043a\u0443\u043f\u0430)",
            body,
        )
        self.assertNotIn("\u041a\u043e\u043d\u0432\u0435\u0440\u0441\u0438\u044f \u0437\u0430\u043a\u0430\u0437 \u2192 \u0432\u044b\u043a\u0443\u043f: 116.7 %", body)


if __name__ == "__main__":
    unittest.main()

