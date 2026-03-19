from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v4.cabinets.paths import (
    build_artifact_subpaths,
    ensure_within_root,
    get_audit_output_dir,
    get_daily_output_dir,
    get_temp_dir,
)


class TestCabinetPaths(unittest.TestCase):
    def test_daily_and_audit_paths_are_deterministic_and_cabinet_aware(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            daily = get_daily_output_dir(
                seller_id="seller_001",
                cabinet_id="cabinet_001",
                run_date="2026-03-15",
                output_root=tmpdir,
                output_subdir="seller_001",
            )
            audit = get_audit_output_dir(
                seller_id="seller_001",
                cabinet_id="cabinet_001",
                run_date="2026-03-15",
                output_root=tmpdir,
                output_subdir="seller_001",
            )

            self.assertIn("seller_001", str(daily))
            self.assertIn("cabinet_001", str(daily))
            self.assertIn("daily", str(daily))
            self.assertIn("audit", str(audit))
            self.assertTrue(str(daily).endswith(str(Path("daily") / "2026-03-15")))
            self.assertTrue(str(audit).endswith(str(Path("audit") / "2026-03-15")))

    def test_temp_path_and_artifact_subpaths_stay_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = get_temp_dir(
                seller_id="seller_001",
                cabinet_id="cabinet_001",
                mode="daily",
                temp_root=tmpdir,
            )
            self.assertTrue(str(temp_path).startswith(str(Path(tmpdir).resolve())))

            artifact_paths = build_artifact_subpaths(Path(tmpdir) / "out")
            for path in artifact_paths.values():
                self.assertTrue(str(path).startswith(str((Path(tmpdir) / "out").resolve())))

    def test_ensure_within_root_blocks_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            ok_target = root / "child"
            self.assertEqual(ensure_within_root(root, ok_target), ok_target.resolve())

            with self.assertRaises(ValueError):
                ensure_within_root(root, root.parent / "escape")


if __name__ == "__main__":
    unittest.main()

