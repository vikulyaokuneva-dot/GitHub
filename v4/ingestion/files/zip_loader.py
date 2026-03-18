"""ZIP input helper skeleton.

Input: archive path and destination directory.
Output: extracted file list metadata.
Does not parse files and does not classify business sources.
"""

from __future__ import annotations

from typing import Dict, List


def extract(archive_path: str, destination_dir: str) -> Dict[str, List[str]]:
    _ = (archive_path, destination_dir)
    return {"files": [], "errors": ["not_implemented_stage_1"]}
