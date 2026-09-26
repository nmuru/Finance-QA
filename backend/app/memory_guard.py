"""Memory capacity protection for long-running analysis work."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)


# class MemoryCapacityError(RuntimeError):
#     """Raised when the service should not start or continue analysis."""

#     code = "MEMORY_CAPACITY"
#     user_message = "Please try again later due to temporary backend memory limitations."

class MemoryCapacityError(RuntimeError):
    """Raised when the service should not start or continue analysis."""

    code = "MEMORY_CAPACITY"
    user_message = "Please try again later due to temporary backend memory limitations."

    def __init__(self, message: str):
        logger.error(
            "MEMORY_CAPACITY_ERROR_CREATED: %s",
            message,
            stack_info=True,
        )
        super().__init__(message)


def _parse_memory_stat(raw: str) -> dict[str, int]:
    """Parse Linux cgroup memory.stat into a simple key/value mapping."""
    stats: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            stats[parts[0]] = int(parts[1])
        except ValueError:
            continue
    return stats


def _cgroup_memory() -> tuple[int | None, int | None, int]:
    """Return (limit, current, reclaimable) bytes for a visible cgroup limit.

    cgroup memory.current includes memory which Linux can reclaim under
    pressure, especially filesystem cache. Treating all of that cache as
    unavailable makes a small container look much closer to OOM than it is.
    The reclaimable figure is therefore derived from memory.stat and is
    only used as additional headroom; the hard cgroup limit remains the
    authoritative ceiling.

    For cgroup v2, file includes tmpfs/shared memory, so subtract shmem
    before treating filesystem cache as reclaimable. Reclaimable slab is also
    included when the kernel exposes it.

    For cgroup v1, cache is the corresponding page-cache statistic.
    """
    candidates = [
        (
            Path("/sys/fs/cgroup/memory.max"),
            Path("/sys/fs/cgroup/memory.current"),
            Path("/sys/fs/cgroup/memory.stat"),
            "v2",
        ),
        (
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
            Path("/sys/fs/cgroup/memory/memory.usage_in_bytes"),
            Path("/sys/fs/cgroup/memory/memory.stat"),
            "v1",
        ),
    ]

    for limit_path, current_path, stat_path, version in candidates:
        try:
            raw_limit = limit_path.read_text(encoding="utf-8").strip()
            if raw_limit == "max":
                continue

            limit = int(raw_limit)
            current = int(current_path.read_text(encoding="utf-8").strip())
            if limit <= 0 or current < 0:
                continue

            reclaimable = 0
            try:
                stats = _parse_memory_stat(stat_path.read_text(encoding="utf-8"))
                if version == "v2":
                    file_cache = max(0, stats.get("file", 0) - stats.get("shmem", 0))
                    reclaimable = file_cache + max(0, stats.get("slab_reclaimable", 0))
                else:
                    reclaimable = max(
                        0,
                        stats.get("cache", 0),
                        stats.get("inactive_file", 0),
                    )
            except (OSError, ValueError):
                # The limit/current values are still useful if memory.stat is
                # unavailable or changes while it is being read.
                pass

            return limit, current, min(reclaimable, current)

        except (OSError, ValueError):
            continue

    return None, None, 0


def memory_snapshot() -> tuple[int, int, int | None]:
    """Return (available, used, limit) bytes using the tightest visible limit."""
    virtual = psutil.virtual_memory()
    available = int(virtual.available)
    used = int(virtual.total - virtual.available)
    limit, current, reclaimable = _cgroup_memory()
    if limit is not None and current is not None:
        # Keep the cgroup limit as the ceiling, but do not count reclaimable
        # cache as permanently consumed capacity.
        effective_used = max(0, current - reclaimable)
        available = max(0, limit - effective_used)
        used = effective_used
    return available, used, limit


def _safe_reserve_bytes(limit: int | None, minimum_mb: int = 256) -> int:
    """Keep a meaningful reserve, including on small hosted containers."""
    if limit is None:
        return minimum_mb * 1024 * 1024
    return max(minimum_mb * 1024 * 1024, int(limit * 0.20))


# def ensure_memory_available(min_available_mb: int = 128, context: str = "analysis") -> None:
#     available, _, limit = memory_snapshot()
#     required = max(min_available_mb * 1024 * 1024, _safe_reserve_bytes(limit, min_available_mb))
#     if available < required:
#         raise MemoryCapacityError(
#             f"Temporary memory capacity is too low to start or continue {context}. "
#             f"Available memory: {available / 1024 / 1024:.0f} MB; "
#             f"required reserve: {required / 1024 / 1024:.0f} MB."
#         )

def ensure_memory_available(
    min_available_mb: int = 128,
    context: str = "analysis",
) -> None:
    available, used, limit = memory_snapshot()

    required = max(
        min_available_mb * 1024 * 1024,
        _safe_reserve_bytes(limit, min_available_mb),
    )

    logger.warning(
        "MEMORY_CHECK context=%s available=%.2f MB used=%.2f MB "
        "limit=%s MB required=%.2f MB min_available=%s MB",
        context,
        available / 1024 / 1024,
        used / 1024 / 1024,
        f"{limit / 1024 / 1024:.2f}" if limit else "None",
        required / 1024 / 1024,
        min_available_mb,
    )

    if available < required:
        logger.warning(
            "MEMORY_CHECK_FAILED available=%.2f MB required=%.2f MB",
            available / 1024 / 1024,
            required / 1024 / 1024,
        )

        raise MemoryCapacityError(
            f"Temporary memory capacity is too low to start or continue {context}. "
            f"Available memory: {available / 1024 / 1024:.0f} MB; "
            f"required reserve: {required / 1024 / 1024:.0f} MB."
        )

def memory_pressure(critical_available_mb: int = 64) -> bool:
    available, used, limit = memory_snapshot()
    reserve = _safe_reserve_bytes(limit, critical_available_mb)
    percent = (used / limit * 100.0) if limit else 0.0
    return available < reserve or percent >= 92.0


class MemoryCapacityGuard:
    """Watch one analysis and request cancellation before an OOM condition."""

    def __init__(self, control, interval_seconds: float = 2.0) -> None:
        self.control = control
        self.interval_seconds = max(0.5, float(interval_seconds))
        self.triggered = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, name=f"memory-guard-{control.run_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self.interval_seconds + 1.0)

    def _watch(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            if self.control.snapshot().get("status") not in {"running", "cancelling"}:
                return
            if not memory_pressure():
                continue
            available, used, limit = memory_snapshot()
            percent = (used / limit * 100.0) if limit else 0.0
            self.triggered.set()
            logger.warning(
                "Memory capacity guard triggered; cancelling analysis work_id=%s: "
                "available=%.0f MB, used=%.0f MB, limit=%s MB, used_percent=%s",
                self.control.run_id,
                available / 1024 / 1024,
                used / 1024 / 1024,
                f"{limit / 1024 / 1024:.0f}" if limit else "unlimited",
                f"{percent:.1f}" if limit else "n/a",
            )
            self.control.cancel()
            return


def capacity_diagnostics() -> dict[str, float | int | None]:
    available, used, limit = memory_snapshot()
    return {
        "pid": os.getpid(),
        "available_mb": round(available / 1024 / 1024, 2),
        "used_mb": round(used / 1024 / 1024, 2),
        "limit_mb": round(limit / 1024 / 1024, 2) if limit else None,
        "used_percent": round((used / limit) * 100, 2) if limit else None,
    }
