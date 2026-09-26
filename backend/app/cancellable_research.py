"""Run semantic research in killable child processes.

Each research request runs in its own child process so cancellation has a hard OS-level
boundary. Repository research failures fail the analysis; phase research failures are
propagated to the owning phase. Neither path uses fallback research content.
"""
from __future__ import annotations

import multiprocessing as mp
import traceback
from pathlib import Path
from queue import Empty
from typing import Any, Callable

from .run_control import RunCancelled, RunControl


def _research_worker(kind: str, kwargs: dict[str, Any], result_queue: Any) -> None:
    try:
        from .semantic_research import run_phase_research, run_repository_research

        function: Callable[..., str]
        if kind == "repository":
            function = run_repository_research
        elif kind == "phase":
            function = run_phase_research
        else:
            raise ValueError(f"Unsupported semantic research kind: {kind}")

        result = function(**kwargs)
        result_queue.put({"ok": True, "result": result})
    except BaseException as exc:
        result_queue.put({"ok": False, "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()})


def _research_failure(kind: str, kwargs: dict[str, Any], error_type: str, error: str) -> RuntimeError:
    if kind == "repository":
        return RuntimeError(f"Repository semantic research failed: {error_type}: {error}")
    return RuntimeError(f"Semantic research failed for phase '{kwargs.get('phase', 'selected phase')}': {error_type}: {error}")


def _run_cancellable(kind: str, kwargs: dict[str, Any], run_control: RunControl | None) -> str:
    if run_control and run_control.is_cancelled():
        raise RunCancelled("Analysis stopped by the user.")

    context = mp.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(target=_research_worker, args=(kind, kwargs, result_queue), daemon=True)
    try:
        process.start()
    except Exception as exc:
        if run_control and run_control.is_cancelled():
            raise RunCancelled("Analysis stopped by the user.") from exc
        raise _research_failure(kind, kwargs, type(exc).__name__, str(exc)) from exc

    payload: dict[str, Any] | None = None
    try:
        while process.is_alive():
            if run_control and run_control.is_cancelled():
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
                raise RunCancelled("Analysis stopped by the user.")
            try:
                payload = result_queue.get_nowait()
                break
            except Empty:
                process.join(timeout=0.1)

        if payload is None:
            if run_control and run_control.is_cancelled():
                raise RunCancelled("Analysis stopped by the user.")
            try:
                payload = result_queue.get(timeout=5)
            except Empty as exc:
                raise _research_failure(kind, kwargs, "SemanticResearchWorkerExit", f"worker exited without a result (exit_code={process.exitcode})") from exc

        if payload.get("ok"):
            result = str(payload.get("result") or "")
            if result.strip():
                return result
            raise _research_failure(kind, kwargs, "SemanticResearchEmptyResult", "research worker returned an empty result")

        error_type = str(payload.get("error_type", "SemanticResearchError"))
        error = str(payload.get("error", "semantic research failed"))
        raise _research_failure(kind, kwargs, error_type, error)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        try:
            result_queue.close()
            result_queue.join_thread()
        except (AttributeError, OSError):
            pass


def run_repository_research(*, intelligence: Any, repository: Path, provider: str, model: str, api_key: str, run_control: RunControl | None = None) -> str:
    return _run_cancellable("repository", {"intelligence": intelligence, "repository": repository, "provider": provider, "model": model, "api_key": api_key}, run_control)


def run_phase_research(*, phase: str, phase_intelligence: str, repository_research: str, repository: Path, provider: str, model: str, api_key: str, run_control: RunControl | None = None) -> str:
    return _run_cancellable("phase", {"phase": phase, "phase_intelligence": phase_intelligence, "repository": repository, "provider": provider, "model": model, "api_key": api_key, "repository_research": repository_research}, run_control)
