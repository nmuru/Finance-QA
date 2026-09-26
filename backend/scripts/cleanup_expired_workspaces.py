"""Remove completed analysis workspaces older than the configured retention period.

Run manually from any working directory, for example:
    python backend/scripts/cleanup_expired_workspaces.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402


def output_root() -> Path:
    root = Path(settings.analysis_results_dir)
    return root if root.is_absolute() else BACKEND_DIR / root


def parse_completed_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def cleanup_expired_workspaces(now: datetime | None = None) -> int:
    root = output_root()
    if not root.is_dir():
        print(f"Workspace directory does not exist: {root}")
        return 0

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(hours=settings.workspace_retention_hours)
    deleted = 0

    for run_dir in root.iterdir():
        if not run_dir.is_dir():
            continue

        state_path = run_dir / "run-state.json"
        if not state_path.is_file():
            continue

        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(f"Skipping unreadable state: {state_path}")
            continue

        if state.get("status") != "completed":
            continue

        completed_at = parse_completed_at(state.get("completed_at"))
        if completed_at is None:
            # Never delete a workspace when the new timestamp is absent or invalid.
            continue
        if completed_at > cutoff:
            continue

        try:
            shutil.rmtree(run_dir)
        except OSError as exc:
            print(f"Unable to delete {run_dir}: {exc}")
            continue

        deleted += 1
        print(f"Deleted expired workspace: {run_dir} (completed_at={completed_at.isoformat()})")

    print(f"Cleanup complete. Deleted {deleted} workspace(s); retention={settings.workspace_retention_hours:g}h.")
    return deleted


if __name__ == "__main__":
    cleanup_expired_workspaces()
