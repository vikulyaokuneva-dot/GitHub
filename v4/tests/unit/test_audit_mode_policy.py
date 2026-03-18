from __future__ import annotations

import unittest

from v4.pipeline.modes.audit_file_mode import (
    MODE_DESCRIPTOR,
    get_audit_mode_flags,
    get_optional_file_inputs,
    get_required_file_inputs,
    get_required_raw_sources,
    is_allowed_source,
)


class TestAuditModePolicy(unittest.TestCase):
    def test_audit_mode_is_file_only(self) -> None:
        flags = get_audit_mode_flags()
        self.assertEqual(flags["mode"], "audit_file_mode")
        self.assertFalse(flags["api_ingestion_enabled"])
        self.assertTrue(flags["file_ingestion_only"])
        self.assertTrue(flags["limited_mode"])

    def test_required_and_optional_file_inputs(self) -> None:
        self.assertEqual(set(get_required_file_inputs()), {"daily_report"})
        self.assertEqual(set(get_optional_file_inputs()), {"funnel_report", "ads_report"})

    def test_allowed_sources_are_audit_file_raw_only(self) -> None:
        self.assertEqual(set(get_required_raw_sources()), {"realization"})
        self.assertTrue(is_allowed_source("orders"))
        self.assertTrue(is_allowed_source("sales"))
        self.assertTrue(is_allowed_source("realization"))
        self.assertTrue(is_allowed_source("stocks"))
        self.assertTrue(is_allowed_source("funnel"))
        self.assertTrue(is_allowed_source("ads"))
        self.assertFalse(is_allowed_source("ads_campaigns"))
        self.assertFalse(is_allowed_source("unknown"))

    def test_descriptor_contains_disclaimer(self) -> None:
        self.assertIn("audit_file_mode", MODE_DESCRIPTOR.disclaimer)


if __name__ == "__main__":
    unittest.main()
