import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .agent_runner import AgentRunnerError
from .analyzer import analyze_repository
from .config import settings
from .memory_guard import MemoryCapacityError, MemoryCapacityGuard, capacity_diagnostics
from .exporter import create_download_package
from .edgar_financials import EdgarFinancialsError, collect_financial_statements
from .run_control import RunCancelled, RunControl, load_persisted_run
from .schemas import AnalyzeRequest

logger = logging.getLogger(__name__)

app = FastAPI(title="ReverseEngineer-SDLC API", version="0.2.0")
app.add_middleware(CORSMiddleware, 
                #    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()], 
                   allow_origins="https://financial-dossier.vercel.app",
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_run_controls: dict[str, RunControl] = {}
_run_controls_lock = Lock()
UI_HEARTBEAT_TIMEOUT_SECONDS = 60.0
UI_HEARTBEAT_SCAN_SECONDS = 5.0
MEMORY_MIN_AVAILABLE_MB = 128
MEMORY_CHECK_INTERVAL_SECONDS = 2.0


def _output_root() -> Path:
    root = Path(settings.analysis_results_dir)
    return root if root.is_absolute() else Path(__file__).resolve().parents[1] / root


def _run_dir(work_id: str) -> Path:
    if Path(work_id).name != work_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _output_root() / work_id


def _cleanup_run_dir(work_id: str) -> bool:
    run_dir = _run_dir(work_id)
    if not run_dir.exists():
        return False
    shutil.rmtree(run_dir)
    return True


def _wait_for_terminal(control: RunControl, timeout_seconds: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = control.snapshot()
        if state.get("status") in {"completed", "failed", "cancelled"}:
            return state
        time.sleep(0.2)
    raise TimeoutError(f"Analysis did not terminate within {timeout_seconds:.0f} seconds.")


def _cleanup_orphaned_run(control: RunControl) -> None:
    try:
        _wait_for_terminal(control)
        _cleanup_run_dir(control.run_id)
    except TimeoutError:
        logger.error("Orphaned UI run did not terminate within timeout; retaining output for safety work_id=%s", control.run_id)
        return
    except OSError:
        logger.exception("Unable to clean orphaned UI output work_id=%s", control.run_id)
        return
    with _run_controls_lock:
        _run_controls.pop(control.run_id, None)
    logger.info("Removed orphaned UI workspace work_id=%s", control.run_id)


def _ui_heartbeat_watchdog() -> None:
    while True:
        time.sleep(UI_HEARTBEAT_SCAN_SECONDS)
        with _run_controls_lock:
            controls = list(_run_controls.values())
        for control in controls:
            state = control.snapshot()
            if state.get("status") not in {"running", "cancelling"}:
                continue
            if control.heartbeat_age_seconds() <= UI_HEARTBEAT_TIMEOUT_SECONDS:
                continue
            if control.cancel():
                logger.warning("UI heartbeat lost; hard-cancelling analysis work_id=%s", control.run_id)
                Thread(target=_cleanup_orphaned_run, args=(control,), daemon=True).start()


def _read_phase_result(run_id: str, phase: str) -> str | None:
    if Path(run_id).name != run_id or Path(phase).name != phase:
        return None
    path = _output_root() / run_id / phase / "raw.md"
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if content.startswith("---\n"):
        parts = content.split("---\n", 2)
        if len(parts) == 3:
            content = parts[2]
    return content.strip()


Thread(target=_ui_heartbeat_watchdog, daemon=True).start()


@app.get("/api/financials/{identifier}")
def financial_statements(identifier: str, periods: int = 5, view: str = "standard") -> dict[str, Any]:
    """Return deterministic SEC financial statements collected through EdgarTools."""
    try:
        return collect_financial_statements(identifier, historical_periods=periods, view=view)
    except EdgarFinancialsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    snapshot = capacity_diagnostics()
    return {"status": "ok", "memory": snapshot}


@app.get("/api/analysis/{work_id}/status")
def analysis_status(work_id: str) -> dict[str, Any]:
    if Path(work_id).name != work_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    with _run_controls_lock:
        control = _run_controls.get(work_id)
    if control:
        control.touch()
    state = control.snapshot() if control else load_persisted_run(_output_root() / work_id / "run-state.json")
    if state is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    completed = list(state.get("completed_phases", []))
    results = {phase: content for phase in completed if (content := _read_phase_result(work_id, phase)) is not None}
    return {**state, "results": results}


@app.post("/api/analysis/{work_id}/stop")
def stop_analysis(work_id: str) -> dict[str, Any]:
    if Path(work_id).name != work_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    with _run_controls_lock:
        control = _run_controls.get(work_id)
    if control is None:
        state = load_persisted_run(_output_root() / work_id / "run-state.json")
        if state is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        if state.get("status") in {"completed", "failed", "cancelled"}:
            return state
        raise HTTPException(status_code=409, detail="The analysis is no longer attached to this server process and cannot be stopped here.")
    control.touch()
    control.cancel()
    return control.snapshot()


@app.post("/api/analysis/{work_id}/close")
def close_analysis(work_id: str) -> dict[str, Any]:
    """Hard-close a UI workspace: cancel its run, wait for termination, then delete all run output."""
    run_dir = _run_dir(work_id)
    with _run_controls_lock:
        control = _run_controls.get(work_id)

    if control is not None:
        state = control.snapshot()
        if state.get("status") in {"running", "cancelling"}:
            control.cancel()
            try:
                state = _wait_for_terminal(control)
            except TimeoutError as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
    else:
        state = load_persisted_run(run_dir / "run-state.json")
        if state is None:
            if not run_dir.exists():
                return {"run_id": work_id, "deleted": False, "already_closed": True}
            state = {"status": "unknown"}

    try:
        deleted = _cleanup_run_dir(work_id)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to clean analysis output: {exc}") from exc

    with _run_controls_lock:
        _run_controls.pop(work_id, None)

    return {"run_id": work_id, "runtime_mode": settings.runtime_mode, "retained": False, "cleanup_scheduled": False, "deleted": deleted, "terminal_status": state.get("status")}


@app.get("/api/analysis/{work_id}/download")
def download_analysis(work_id: str) -> FileResponse:
    if Path(work_id).name != work_id:
        raise HTTPException(status_code=404, detail="Analysis download not found")

    run_dir = _output_root() / work_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Analysis download not found")

    # Rebuild on demand so the download remains available even if a previous
    # per-phase export was interrupted or the run predates the package logic.
    # create_download_package serialises concurrent exports with phase completion.
    try:
        zip_path = create_download_package(run_dir)
    except (FileNotFoundError, OSError) as exc:
        logger.warning("Unable to create analysis download work_id=%s: %s", work_id, exc)
        raise HTTPException(status_code=404, detail="Analysis download not found") from exc

    return FileResponse(zip_path, media_type="application/zip", filename="financial-analysis.zip")


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> StreamingResponse:
    """Run the analysis pipeline and stream completed phases and actionable failures."""
    company_name = request.company_name
    event_queue: Queue[dict[str, Any]] = Queue()
    requested_run_id = request.work_id

    if requested_run_id:
        with _run_controls_lock:
            existing = _run_controls.get(requested_run_id)
        if existing and existing.snapshot().get("status") in {"running", "cancelling"}:
            raise HTTPException(status_code=409, detail="An analysis with this work ID is already running.")

    if request.mode not in {"parallel", "sequence"}:
        raise HTTPException(status_code=422, detail="mode must be 'parallel' or 'sequence'")

    try:
        try:
            ensure_available = __import__("app.memory_guard", fromlist=["ensure_memory_available"]).ensure_memory_available
            ensure_available(MEMORY_MIN_AVAILABLE_MB, "analysis")
        except MemoryCapacityError as exc:
            logger.warning("Rejecting analysis because backend memory capacity is low: %s", exc)
            raise HTTPException(status_code=503, detail=exc.user_message) from exc

        resolved_run_id = requested_run_id or __import__("uuid").uuid4().hex
        output_run_dir = _output_root() / resolved_run_id
        output_run_dir.mkdir(parents=True, exist_ok=True)
        control = RunControl(resolved_run_id, output_run_dir / "run-state.json")
        control.initialize(company_name=company_name, selected_phases=request.selected_phases)
        with _run_controls_lock:
            _run_controls[resolved_run_id] = control
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to initialize analysis workspace: {exc}") from exc

    memory_guard = MemoryCapacityGuard(control, MEMORY_CHECK_INTERVAL_SECONDS)
    memory_guard.start()
    stream_run_id = {"value": resolved_run_id}

    def on_phase_complete(phase_result: dict) -> None:
        event_queue.put({"type": "phase_completed", "phase": phase_result["phase"], "phase_name": phase_result["phase_name"], "raw_analysis": phase_result["raw_analysis"], "raw_path": phase_result["raw_path"], "run_id": phase_result["run_id"], "provenance": phase_result.get("provenance")})

    def run_analysis() -> None:
        try:
            results = analyze_repository(company_name, phases_per_batch=settings.phases_per_batch, batch_mode=request.mode, selected_phases=request.selected_phases, work_id=resolved_run_id, on_phase_complete=on_phase_complete, provider=request.provider, model=request.model, api_key=request.api_key, run_control=control, objective=request.objective)
            if control.is_cancelled():
                if memory_guard.triggered.is_set():
                    control.finish("failed", MemoryCapacityError.user_message)
                    logger.warning("Analysis stopped by memory capacity guard work_id=%s", resolved_run_id)
                    event_queue.put({"type": "analysis_failed", "company_name": company_name, "run_id": resolved_run_id, "error": MemoryCapacityError.user_message})
                else:
                    control.finish("cancelled")
                    event_queue.put({"type": "analysis_cancelled", "company_name": company_name, "run_id": resolved_run_id, "completed_phases": list(results["results"].keys()), "failed_phases": results.get("failures", [])})
            else:
                control.finish("completed")
                event_queue.put({"type": "analysis_completed", "company_name": company_name, "run_id": results["run_id"], "completed_phases": list(results["results"].keys()), "failed_phases": results.get("failures", [])})
        except RunCancelled:
            if memory_guard.triggered.is_set():
                control.finish("failed", MemoryCapacityError.user_message)
                logger.warning("Analysis stopped by memory capacity guard work_id=%s", control.run_id)
                event_queue.put({"type": "analysis_failed", "company_name": company_name, "run_id": control.run_id, "error": MemoryCapacityError.user_message})
            else:
                control.finish("cancelled")
                event_queue.put({"type": "analysis_cancelled", "company_name": company_name, "run_id": control.run_id, "completed_phases": list(control.snapshot()["completed_phases"]), "failed_phases": control.snapshot()["failures"]})
        except (AgentRunnerError, ValueError) as exc:
            control.finish("failed", str(exc))
            event_queue.put({"type": "analysis_failed", "company_name": company_name, "run_id": control.run_id, "error": str(exc)})
        except Exception as exc:
            control.finish("failed", f"Analysis failed due to an unexpected backend error: {type(exc).__name__}: {exc}")
            logger.exception("Unexpected analysis failure: company_name=%s", company_name)
            event_queue.put({"type": "analysis_failed", "company_name": company_name, "run_id": control.run_id, "error": f"Analysis failed due to an unexpected backend error: {type(exc).__name__}: {exc}"})
        finally:
            memory_guard.stop()

    Thread(target=run_analysis, daemon=True).start()

    async def event_stream():
        while True:
            current_run_id = stream_run_id["value"]
            with _run_controls_lock:
                active_control = _run_controls.get(current_run_id) if current_run_id else None
            if active_control:
                active_control.touch()
            try:
                event = await asyncio.to_thread(event_queue.get, True, 1.0)
            except Empty:
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event["type"] in {"analysis_completed", "analysis_failed", "analysis_cancelled"}:
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no-cache"})
