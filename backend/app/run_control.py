"""Per-analysis run state and cancellation controls."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .exporter import create_download_package


_persist_lock = threading.Lock()


class RunControl:
    def __init__(self, run_id: str, state_path: Path) -> None:
        self.run_id = run_id
        self.state_path = state_path
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self.status = "running"
        self.company_name = ""
        self.selected_phases: list[str] = []
        self.completed_phases: list[str] = []
        self.failures: list[dict[str, Any]] = []
        self.error: str | None = None
        self.active_phase: Optional[str] = None
        self.completed_at: str | None = None
        self.last_heartbeat = time.monotonic()

    def initialize(self, *, company_name: str, selected_phases: list[str]) -> None:
        previous_completed: list[str] = []
        try:
            if self.state_path.is_file():
                previous = json.loads(self.state_path.read_text(encoding="utf-8"))
                previous_company = previous.get("company_name") or previous.get("repo_url")
                if previous_company == company_name and previous.get("status") in {"completed", "failed", "cancelled"}:
                    previous_completed = list(previous.get("completed_phases", []))
        except (OSError, json.JSONDecodeError, TypeError):
            previous_completed = []

        self.status = "running"
        self.company_name = company_name
        self.selected_phases = list(selected_phases)
        self.completed_phases = previous_completed
        self.failures = []
        self.error = None
        self.active_phase = selected_phases[0] if selected_phases else None
        self.completed_at = None
        self.cancel_event.clear()
        self.last_heartbeat = time.monotonic()
        self.persist()

    def touch(self) -> None:
        with self._lock:
            self.last_heartbeat = time.monotonic()

    def heartbeat_age_seconds(self) -> float:
        with self._lock:
            return max(0.0, time.monotonic() - self.last_heartbeat)

    def cancel(self) -> bool:
        with self._lock:
            if self.status in {"completed", "failed", "cancelled"}:
                return False
            self.status = "cancelling"
            self.cancel_event.set()
        self.persist()
        return True

    def phase_started(self, phase: str) -> None:
        with self._lock:
            self.active_phase = phase
        self.persist()

    def phase_completed(self, phase: str) -> None:
        with self._lock:
            if phase not in self.completed_phases:
                self.completed_phases.append(phase)
            self.active_phase = None
        self.persist()
        try:
            create_download_package(self.state_path.parent)
        except OSError:
            pass

    def phase_failed(self, failure: dict[str, Any]) -> None:
        with self._lock:
            self.failures = [item for item in self.failures if item.get("phase") != failure.get("phase")]
            self.failures.append(failure)
            self.active_phase = None
        self.persist()

    def finish(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self.status = status
            self.error = error
            self.active_phase = None
            self.completed_at = datetime.now(timezone.utc).isoformat() if status == "completed" else None
        self.persist()

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "status": self.status,
                "company_name": self.company_name,
                "selected_phases": list(self.selected_phases),
                "completed_phases": list(self.completed_phases),
                "failures": list(self.failures),
                "error": self.error,
                "active_phase": self.active_phase,
                "completed_at": self.completed_at,
            }

    def persist(self) -> None:
        payload = self.snapshot()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".tmp")
        with _persist_lock:
            temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_path.replace(self.state_path)


class RunCancelled(Exception):
    """Raised when the user cancels an analysis run."""


def load_persisted_run(state_path: Path) -> dict[str, Any] | None:
    if not state_path.is_file():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
