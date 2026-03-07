from __future__ import annotations

import os


def _ensure(path: str, create: bool) -> str:
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def cabinet_root(repo_root: str, seller_id: str, create: bool = True) -> str:
    return _ensure(os.path.join(repo_root, "cabinets", seller_id), create=create)


def artifacts_dir(repo_root: str, seller_id: str, create: bool = True) -> str:
    return _ensure(os.path.join(cabinet_root(repo_root, seller_id, create=create), "artifacts"), create=create)


def reports_dir(repo_root: str, seller_id: str, create: bool = True) -> str:
    return _ensure(os.path.join(cabinet_root(repo_root, seller_id, create=create), "reports"), create=create)


def input_dir(repo_root: str, seller_id: str, create: bool = True) -> str:
    return _ensure(os.path.join(cabinet_root(repo_root, seller_id, create=create), "input"), create=create)
