def format_run_summary(task_id: str, status: str, run_dir: str, applied_files: list[str], violations: list[dict]) -> str:
    """Return a human‑readable multi‑line summary of a run.

    Parameters
    ----------
    task_id: str
        Identifier of the task that was executed.
    status: str
        Final status of the run (e.g., "success", "failed").
    run_dir: str
        Path to the directory where run artefacts are stored.
    applied_files: list[str]
        List of file paths that were created or modified during the run.
    violations: list[dict]
        List of violation dictionaries. Each dict is expected to contain at
        least a ``"type"`` and a ``"message"`` key.

    Returns
    -------
    str
        A formatted multi‑line string suitable for logging or console output.
    """
    lines = []
    lines.append(f"Run Summary for task '{task_id}'")
    lines.append(f"Status      : {status}")
    lines.append(f"Run directory: {run_dir}")
    lines.append("")

    # Applied files section
    lines.append("Applied files:")
    if applied_files:
        for f in applied_files:
            lines.append(f"  - {f}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Violations section
    lines.append("Violations:")
    if violations:
        for i, v in enumerate(violations, start=1):
            v_type = v.get("type", "unknown")
            v_msg = v.get("message", "")
            lines.append(f"  {i}. [{v_type}] {v_msg}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)
