"""Application-level smoke-test diagnostics for the embedded OpenAI Agents SDK.

Run this against a locally running backend. It sends concurrent one-phase
analysis requests and samples the backend process tree and RSS while requests
are active. The diagnostic is intentionally independent of Claude/OpenCode
process names: the key measurement is whether application requests create
additional OS processes at all.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import psutil
import requests

BACKEND_URL = os.getenv("SMOKE_BACKEND_URL", "http://127.0.0.1:8000")
REQUESTS = int(os.getenv("SMOKE_CONCURRENT_REQUESTS", "3"))
SAMPLE_SECONDS = float(os.getenv("SMOKE_SAMPLE_INTERVAL", "0.5"))
PHASE = os.getenv("SMOKE_PHASE", "business_purpose")
REPO_URL = os.getenv(
    "SMOKE_REPO_URL",
    "https://github.com/nmuru/continuous-delivery-cloud-native-java-apps-2423655",
)


@dataclass
class Snapshot:
    root_rss_mb: float
    descendants: int
    descendant_rss_mb: float


def _mb(value: int) -> float:
    return round(value / (1024 * 1024), 1)


def _backend_processes() -> list[psutil.Process]:
    """Locate processes listening on the configured backend port."""
    from urllib.parse import urlparse

    parsed = urlparse(BACKEND_URL)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    found: dict[int, psutil.Process] = {}

    for connection in psutil.net_connections(kind="inet"):
        if not connection.laddr or connection.laddr.port != port:
            continue
        if not connection.pid:
            continue
        try:
            process = psutil.Process(connection.pid)
            found[process.pid] = process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return list(found.values())


def _snapshot(processes: list[psutil.Process]) -> Snapshot:
    roots: dict[int, psutil.Process] = {p.pid: p for p in processes}
    descendants: dict[int, psutil.Process] = {}

    root_rss = 0
    descendant_rss = 0

    for process in roots.values():
        try:
            root_rss += process.memory_info().rss
            for child in process.children(recursive=True):
                descendants[child.pid] = child
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    for process in descendants.values():
        try:
            descendant_rss += process.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return Snapshot(_mb(root_rss), len(descendants), _mb(descendant_rss))


def _consume_sse(index: int) -> dict[str, Any]:
    payload = {
        "repo_url": REPO_URL,
        "selected_phases": [PHASE],
        "provider": "openrouter",
        "model": "openrouter/free",
        "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "work_id": f"smoke-{int(time.time())}-{index}",
    }

    if not payload["api_key"]:
        raise RuntimeError("OPENROUTER_API_KEY is required for the smoke diagnostic")

    with requests.post(
        f"{BACKEND_URL}/api/analyze",
        json=payload,
        stream=True,
        timeout=600,
    ) as response:
        response.raise_for_status()
        for raw in response.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            event = json.loads(raw[6:])
            if event["type"] == "analysis_failed":
                raise RuntimeError(event["error"])
            if event["type"] == "analysis_completed":
                return event

    raise RuntimeError("Backend closed the stream without a terminal event")


def main() -> None:
    print("OpenAI Agents SDK application smoke-test diagnostics")
    print(f"Python executable: {sys.executable}")
    print(f"Diagnostic PID: {os.getpid()}")
    print(f"Backend: {BACKEND_URL}")
    print(f"Concurrent application requests: {REQUESTS}")
    print(f"Phase: {PHASE}")
    print(f"Sample interval: {SAMPLE_SECONDS} seconds")

    processes = _backend_processes()
    if not processes:
        raise SystemExit("No backend process is listening on the configured port")

    before = _snapshot(processes)
    print("\nBefore requests:")
    print(f"Backend root RSS: {before.root_rss_mb} MB")
    print(f"Backend descendants: {before.descendants}")
    print(f"Backend descendant RSS: {before.descendant_rss_mb} MB")

    stop_monitor = threading.Event()
    maximum_descendants = before.descendants
    maximum_descendant_rss = before.descendant_rss_mb
    maximum_root_rss = before.root_rss_mb

    def monitor() -> None:
        nonlocal maximum_descendants, maximum_descendant_rss, maximum_root_rss
        sample = 0
        while not stop_monitor.wait(SAMPLE_SECONDS):
            sample += 1
            snap = _snapshot(_backend_processes())
            maximum_descendants = max(maximum_descendants, snap.descendants)
            maximum_descendant_rss = max(maximum_descendant_rss, snap.descendant_rss_mb)
            maximum_root_rss = max(maximum_root_rss, snap.root_rss_mb)
            print(
                f"MONITOR sample={sample} backend_descendants={snap.descendants} "
                f"descendant_rss={snap.descendant_rss_mb} MB "
                f"root_rss={snap.root_rss_mb} MB"
            )

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    results: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=REQUESTS) as executor:
            futures = [executor.submit(_consume_sse, index + 1) for index in range(REQUESTS)]
            for future in as_completed(futures):
                results.append(future.result())
    finally:
        stop_monitor.set()
        monitor_thread.join(timeout=2)

    after = _snapshot(_backend_processes())

    print("\nResults:")
    for result in results:
        print(f"completed_phases={result.get('completed_phases')}")

    print("\nConcurrency summary:")
    print(f"Maximum backend descendant processes: {maximum_descendants}")
    print(f"Maximum backend descendant RSS: {maximum_descendant_rss} MB")
    print(f"Maximum backend root RSS: {maximum_root_rss} MB")
    print(f"Requested concurrent requests: {REQUESTS}")

    print("\nAfter requests:")
    print(f"Backend root RSS: {after.root_rss_mb} MB")
    print(f"Backend descendants: {after.descendants}")
    print(f"Backend descendant RSS: {after.descendant_rss_mb} MB")


if __name__ == "__main__":
    main()
