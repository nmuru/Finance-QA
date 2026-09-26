"""Lightweight runtime resource diagnostics for pipeline smoke/performance tests.

The monitor samples the FastAPI process, its descendant process tree, and host
memory/CPU and appends JSONL records. It is disabled by configuration by
default so normal application runs are unaffected.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psutil

logger = logging.getLogger(__name__)


class ResourceDiagnostics:
    """Record periodic process-tree/system resource samples and phase events."""

    def __init__(
        self,
        enabled: bool,
        output_dir: str | Path,
        sample_interval_seconds: float = 2.0,
        run_id: Optional[str] = None,
    ) -> None:
        self.enabled = enabled
        self.output_dir = Path(output_dir)
        self.sample_interval_seconds = max(float(sample_interval_seconds), 0.25)
        self.run_id = run_id
        self._process = psutil.Process(os.getpid())
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._file = None
        self._active_phases: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            suffix = self.run_id or "runtime"
            log_path = self.output_dir / f"resource-diagnostics-{suffix}-{timestamp}.jsonl"
            self._file = log_path.open("a", encoding="utf-8")
            self._write_record({"event": "monitor_started"})
            self._process.cpu_percent(interval=None)
            self._thread = threading.Thread(
                target=self._sample_loop,
                name="resource-diagnostics",
                daemon=True,
            )
            self._thread.start()
            logger.info("Resource diagnostics enabled: %s", log_path)
        except Exception:
            logger.exception("Unable to start resource diagnostics")
            self.enabled = False
            self._close_file()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=max(self.sample_interval_seconds + 1.0, 2.0))
        self._thread = None
        self._write_record({"event": "monitor_stopped"})
        self._close_file()

    def phase_start(self, phase: str, phase_name: str, batch_index: Optional[int] = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._active_phases[phase] = {
                "phase": phase,
                "phase_name": phase_name,
                "batch_index": batch_index,
                "started_at": self._now(),
            }
        self._write_record({
            "event": "phase_started",
            "phase": phase,
            "phase_name": phase_name,
            "batch_index": batch_index,
        })

    def phase_end(
        self,
        phase: str,
        phase_name: str,
        batch_index: Optional[int] = None,
        status: str = "completed",
    ) -> None:
        if not self.enabled:
            return
        with self._lock:
            started = self._active_phases.pop(phase, None)
        record: dict[str, Any] = {
            "event": "phase_finished",
            "phase": phase,
            "phase_name": phase_name,
            "batch_index": batch_index,
            "status": status,
        }
        if started is not None:
            record["started_at"] = started["started_at"]
        self._write_record(record)

    def run_event(self, event: str, **context: Any) -> None:
        if self.enabled:
            self._write_record({"event": event, **context})

    def _sample_loop(self) -> None:
        while not self._stop_event.wait(self.sample_interval_seconds):
            self.sample()

    def _collect_process_tree(self) -> dict[str, Any]:
        processes: list[dict[str, Any]] = []
        seen: set[int] = set()
        total_rss = total_private = 0
        total_cpu = 0.0
        try:
            candidates = [self._process, *self._process.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            candidates = [self._process]
        for proc in candidates:
            try:
                if proc.pid in seen or not proc.is_running():
                    continue
                seen.add(proc.pid)
                memory = proc.memory_info()
                cpu = proc.cpu_percent(interval=None)
                private = getattr(memory, "private", 0)
                total_rss += memory.rss
                total_private += private
                total_cpu += cpu
                try:
                    name = proc.name()
                    cmdline = " ".join(proc.cmdline())[:500]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    name, cmdline = "<unavailable>", ""
                processes.append({
                    "pid": proc.pid,
                    "name": name,
                    "rss_mb": round(memory.rss / 1024 / 1024, 2),
                    "private_mb": round(private / 1024 / 1024, 2),
                    "cpu_percent": round(cpu, 2),
                    "cmdline": cmdline,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {
            "root_pid": self._process.pid,
            "process_count": len(processes),
            "total_rss_mb": round(total_rss / 1024 / 1024, 2),
            "total_private_mb": round(total_private / 1024 / 1024, 2),
            "total_cpu_percent": round(total_cpu, 2),
            "processes": processes,
        }

    def sample(self) -> None:
        if not self.enabled:
            return
        try:
            process_tree = self._collect_process_tree()
            virtual = psutil.virtual_memory()
            with self._lock:
                active_phases = list(self._active_phases.values())
            self._write_record({
                "event": "sample",
                "process_tree": process_tree,
                "system": {
                    "total_ram_mb": round(virtual.total / 1024 / 1024, 2),
                    "available_ram_mb": round(virtual.available / 1024 / 1024, 2),
                    "used_ram_mb": round(virtual.used / 1024 / 1024, 2),
                    "percent_used": round(virtual.percent, 2),
                },
                "active_phases": active_phases,
            })
        except Exception:
            logger.exception("Resource diagnostics sample failed")

    def _write_record(self, record: dict[str, Any]) -> None:
        if self._file is None:
            return
        payload = {"timestamp": self._now(), "run_id": self.run_id, **record}
        try:
            with self._lock:
                self._file.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._file.flush()
        except Exception:
            logger.exception("Unable to write resource diagnostics record")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _close_file(self) -> None:
        if self._file is None:
            return
        try:
            with self._lock:
                self._file.close()
        finally:
            self._file = None
