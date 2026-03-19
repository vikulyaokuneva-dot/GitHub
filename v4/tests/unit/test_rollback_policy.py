from __future__ import annotations

import unittest

from v4.production.contracts import ProductionMode
from v4.production.rollback import build_rollback_note, can_rollback, get_rollback_mode


class TestRollbackPolicy(unittest.TestCase):
    def test_rollback_policy_is_deterministic(self) -> None:
        allowed = can_rollback(
            selected_mode=ProductionMode.V4,
            runner_failed=True,
            fallback_allowed=True,
            operator_forced_mode=False,
        )
        denied = can_rollback(
            selected_mode=ProductionMode.V4,
            runner_failed=True,
            fallback_allowed=False,
            operator_forced_mode=True,
        )
        self.assertTrue(allowed)
        self.assertFalse(denied)
        self.assertEqual(get_rollback_mode(ProductionMode.V4), ProductionMode.LEGACY)

    def test_rollback_note_is_populated(self) -> None:
        note = build_rollback_note(
            selected_mode=ProductionMode.V4,
            rollback_mode=ProductionMode.LEGACY,
            reason="runner failure",
            fallback_allowed=True,
        )
        self.assertIn("rollback: v4 -> legacy", note)
        self.assertIn("reason=runner failure", note)

    def test_no_silent_fallback_when_not_allowed(self) -> None:
        self.assertFalse(
            can_rollback(
                selected_mode=ProductionMode.V4,
                runner_failed=True,
                fallback_allowed=False,
                operator_forced_mode=False,
            )
        )


if __name__ == "__main__":
    unittest.main()

