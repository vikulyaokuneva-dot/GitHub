"""ZIP input helpers for audit-mode file ingestion.

Input: archive path and controlled destination directory.
Output: extracted file list metadata.
Does not parse files.
"""

from __future__ import annotations

from pathlib import Path
import zipfile
from typing import Any


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def extract(archive_path: str, destination_dir: str) -> dict[str, Any]:
    archive = Path(archive_path)
    destination = Path(destination_dir)
    destination.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        return {"files": [], "errors": [f"archive not found: {archive}"], "extracted_dir": str(destination)}
    if not zipfile.is_zipfile(archive):
        return {"files": [], "errors": [f"not a zip archive: {archive}"], "extracted_dir": str(destination)}

    extracted: list[str] = []
    errors: list[str] = []
    with zipfile.ZipFile(archive, "r") as zf:
        for member in zf.infolist():
            member_path = destination / member.filename
            if not _is_within(destination, member_path):
                errors.append(f"skipped unsafe zip member: {member.filename}")
                continue
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
                continue
            member_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as source, member_path.open("wb") as target:
                target.write(source.read())
            extracted.append(str(member_path))

    return {"files": extracted, "errors": errors, "extracted_dir": str(destination)}

