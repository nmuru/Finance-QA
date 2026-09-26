"""Financial analysis orchestration.

The deterministic layer acquires SEC Company Facts and collects normalized
financial statements with EdgarTools. The LLM agent retrieves evidence through
bounded tools and performs the actual financial reasoning. No preliminary LLM
summary or second rendering LLM is used.
"""

import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from .agent_runner import run_phase_agent
from .cancellable_download import download_company_facts
from .config import settings
from .edgar_financials import collect_financial_statements
from .exporter import create_download_package
from .phase_intelligence import build_phase_intelligence
from .resource_diagnostics import ResourceDiagnostics
from .run_control import RunCancelled, RunControl

PHASES = [
    ("revenue-earnings-engine", "Revenue & Earnings Engine"),
    ("financial-resilience", "Financial Resilience"),
    ("capital-cash-deployment", "Capital & Cash Deployment"),
    ("accounting-signals-anomalies", "Accounting Signals & Anomalies"),
]
PhaseCompleteCallback = Callable[[dict], None]


def _check_cancelled(run_control: Optional[RunControl]) -> None:
    if run_control and run_control.is_cancelled():
        raise RunCancelled("Analysis stopped by the user.")


def _phase_failure(phase_key: str, phase_name: str, exc: Exception) -> dict:
    error = str(exc)
    error_lower = error.lower()
    if type(exc).__name__.lower() == "maxturnsexceeded" or "max turns" in error_lower:
        error = f"Max turns exceeded for phase '{phase_name}'. Retry the phase or try a different model."
    return {
        "phase": phase_key,
        "phase_name": phase_name,
        "error_type": type(exc).__name__,
        "error": error,
    }


def _run_single_phase(
    phase_key: str,
    phase_name: str,
    repository: Path,
    phase_intelligence: str,
    output_run_dir: Path,
    run_id: str,
    provider: str,
    model: str,
    api_key: str,
    diagnostics: Optional[ResourceDiagnostics] = None,
    batch_index: Optional[int] = None,
    run_control: Optional[RunControl] = None,
) -> dict:
    _check_cancelled(run_control)
    if diagnostics:
        diagnostics.phase_start(phase_key, phase_name, batch_index=batch_index)
    if run_control:
        run_control.phase_started(phase_key)

    try:
        raw_result, actual_model = run_phase_agent(
            phase=phase_key,
            phase_name=phase_name,
            repository=repository,
            phase_intelligence=phase_intelligence,
            provider=provider,
            model=model,
            api_key=api_key,
            run_control=run_control,
        )
        _check_cancelled(run_control)
        if not raw_result.strip():
            raise RuntimeError(f"Agent returned an empty result for phase '{phase_key}'.")

        phase_output_dir = output_run_dir / phase_key
        phase_output_dir.mkdir(parents=True, exist_ok=True)

        # The phase agent is responsible for the final Markdown artifact.
        # There is deliberately no second LLM rendering pass.
        raw_path = phase_output_dir / "raw.md"
        document = f"---\nmodel: {actual_model}\n---\n\n{raw_result}\n"
        raw_path.write_text(document, encoding="utf-8")
        (phase_output_dir / "agent-output.md").write_text(raw_result, encoding="utf-8")
        (phase_output_dir / "provenance.json").write_text(
            json.dumps({"model": actual_model}, indent=2),
            encoding="utf-8",
        )

        if run_control:
            run_control.phase_completed(phase_key)
        if diagnostics:
            diagnostics.phase_end(
                phase_key,
                phase_name,
                batch_index=batch_index,
                status="completed",
            )

        return {
            "phase": phase_key,
            "phase_name": phase_name,
            "raw_analysis": raw_result,
            "raw_path": str(raw_path),
            "run_id": run_id,
            "provenance": {"model": actual_model},
        }
    except RunCancelled:
        if diagnostics:
            diagnostics.phase_end(
                phase_key,
                phase_name,
                batch_index=batch_index,
                status="cancelled",
            )
        raise
    except Exception as exc:
        if run_control and run_control.is_cancelled():
            if diagnostics:
                diagnostics.phase_end(
                    phase_key,
                    phase_name,
                    batch_index=batch_index,
                    status="cancelled",
                )
            raise RunCancelled("Analysis stopped by the user.")
        if run_control:
            run_control.phase_failed(_phase_failure(phase_key, phase_name, exc))
        if diagnostics:
            diagnostics.phase_end(
                phase_key,
                phase_name,
                batch_index=batch_index,
                status="failed",
            )
        raise


def _run_batch(
    batch: list[tuple[str, str]],
    repository: Path,
    phase_packages: dict[str, str],
    output_run_dir: Path,
    run_id: str,
    on_phase_complete: Optional[PhaseCompleteCallback] = None,
    provider: str = "openrouter",
    model: str = "openrouter/free",
    api_key: str = "",
    diagnostics: Optional[ResourceDiagnostics] = None,
    batch_index: Optional[int] = None,
    run_control: Optional[RunControl] = None,
) -> tuple[dict, list[dict]]:
    results: dict[str, dict] = {}
    failures: list[dict] = []

    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        futures = {}
        for key, name in batch:
            _check_cancelled(run_control)
            future = executor.submit(
                _run_single_phase,
                key,
                name,
                repository,
                phase_packages[key],
                output_run_dir,
                run_id,
                provider,
                model,
                api_key,
                diagnostics,
                batch_index,
                run_control,
            )
            futures[future] = (key, name)

        for future in as_completed(futures):
            key, name = futures[future]
            try:
                result = future.result()
                results[result["phase"]] = result
                if on_phase_complete and not (run_control and run_control.is_cancelled()):
                    on_phase_complete(result)
            except RunCancelled:
                raise
            except Exception as exc:
                failure = _phase_failure(key, name, exc)
                failures.append(failure)
                if run_control:
                    run_control.phase_failed(failure)

    return results, failures


def analyze_repository(
    company_name: str,
    phases_per_batch: int = settings.phases_per_batch,
    number_of_batches: Optional[int] = None,
    batch_mode: str = "parallel",
    on_phase_complete: Optional[PhaseCompleteCallback] = None,
    selected_phases: Optional[list[str]] = None,
    work_id: Optional[str] = None,
    provider: str = "openrouter",
    model: str = "openrouter/free",
    api_key: Optional[str] = None,
    run_control: Optional[RunControl] = None,
    objective: str = "document",
) -> dict:
    if not company_name or not company_name.strip():
        raise ValueError("company_name cannot be empty")
    provider = (provider or "").strip().lower()
    if provider not in {"openrouter", "openai"}:
        raise ValueError("This backend currently supports OpenRouter and OpenAI through the OpenAI Agents SDK")
    if not model or not model.strip():
        raise ValueError("model cannot be empty")
    if not api_key or not api_key.strip():
        raise ValueError("api_key cannot be empty")
    if phases_per_batch < 1:
        raise ValueError("phases_per_batch must be at least 1")
    if batch_mode not in {"parallel", "sequence"}:
        raise ValueError("batch_mode must be 'parallel' or 'sequence'")

    available = {key for key, _ in PHASES}
    if selected_phases is None:
        count = number_of_batches or 1
        selected_ids = [key for key, _ in PHASES[: phases_per_batch * count]]
    else:
        if not selected_phases:
            raise ValueError("selected_phases must contain at least one phase")
        if len(set(selected_phases)) != len(selected_phases):
            raise ValueError("selected_phases must not contain duplicates")
        unknown = set(selected_phases) - available
        if unknown:
            raise ValueError(
                "selected_phases contains unknown phases: " + ", ".join(sorted(unknown))
            )
        selected_ids = selected_phases

    run_id = work_id or uuid.uuid4().hex
    if not run_id.isalnum():
        raise ValueError("work_id must contain only letters and numbers")

    output_root = Path(settings.analysis_results_dir)
    if not output_root.is_absolute():
        output_root = Path(__file__).resolve().parents[1] / output_root
    output_run_dir = output_root / run_id
    output_run_dir.mkdir(parents=True, exist_ok=True)

    diagnostics_dir = Path(settings.resource_diagnostics_dir)
    if not diagnostics_dir.is_absolute():
        diagnostics_dir = output_run_dir / diagnostics_dir
    diagnostics = ResourceDiagnostics(
        enabled=settings.resource_diagnostics_enabled,
        output_dir=diagnostics_dir,
        sample_interval_seconds=settings.resource_diagnostics_interval_seconds,
        run_id=run_id,
    )

    definitions = [(key, dict(PHASES)[key]) for key in selected_ids]
    batches = [
        definitions[i : i + phases_per_batch]
        for i in range(0, len(definitions), phases_per_batch)
    ]

    diagnostics.start()
    diagnostics.run_event(
        "analysis_started",
        selected_phases=selected_ids,
        phases_per_batch=phases_per_batch,
        batch_mode=batch_mode,
        batch_count=len(batches),
        provider=provider,
        model=model,
    )

    results: dict[str, dict] = {}
    failures: list[dict] = []

    try:
        _check_cancelled(run_control)

        with tempfile.TemporaryDirectory(prefix="financial-analysis-") as tmp:
            workspace = Path(tmp)
            diagnostics.run_event("workspace_created", workspace=str(workspace))

            repository = download_company_facts(
                company_name,
                workspace,
                run_control=run_control,
            )
            _check_cancelled(run_control)
            diagnostics.run_event(
                "financial_source_downloaded",
                repository=str(repository),
            )

            # One deterministic collection pass. Actual statement rows are stored
            # outside the LLM context and retrieved later through the financial tool.
            financial_data = collect_financial_statements(
                company_name,
                historical_periods=5,
                view="standard",
            )
            financial_data_json = json.dumps(financial_data, ensure_ascii=False)
            (repository / "financial-data.json").write_text(
                financial_data_json,
                encoding="utf-8",
            )
            (output_run_dir / "financial-intelligence.json").write_text(
                financial_data_json,
                encoding="utf-8",
            )
            diagnostics.run_event(
                "financial_intelligence_collected",
                output_chars=len(financial_data_json),
                source="edgartools",
            )

            phase_packages = {
                key: build_phase_intelligence(financial_data_json, key)
                for key in selected_ids
            }
            diagnostics.run_event(
                "financial_context_ready",
                manifest_chars={key: len(value) for key, value in phase_packages.items()},
                expected_upfront_llm_requests=0,
            )

            if batch_mode == "parallel":
                with ThreadPoolExecutor(max_workers=len(batches)) as executor:
                    futures = {
                        executor.submit(
                            _run_batch,
                            batch,
                            repository,
                            phase_packages,
                            output_run_dir,
                            run_id,
                            on_phase_complete,
                            provider,
                            model,
                            api_key,
                            diagnostics,
                            index,
                            run_control,
                        ): index
                        for index, batch in enumerate(batches, start=1)
                    }
                    for future in as_completed(futures):
                        _check_cancelled(run_control)
                        batch_results, batch_failures = future.result()
                        results.update(batch_results)
                        failures.extend(batch_failures)
            else:
                for index, batch in enumerate(batches, start=1):
                    _check_cancelled(run_control)
                    batch_results, batch_failures = _run_batch(
                        batch,
                        repository,
                        phase_packages,
                        output_run_dir,
                        run_id,
                        on_phase_complete,
                        provider,
                        model,
                        api_key,
                        diagnostics,
                        index,
                        run_control,
                    )
                    results.update(batch_results)
                    failures.extend(batch_failures)

        _check_cancelled(run_control)
        if failures:
            diagnostics.run_event(
                "analysis_failed",
                completed_phases=list(results),
                failed_phases=[failure["phase"] for failure in failures],
            )
            create_download_package(output_run_dir)
            return {"run_id": run_id, "results": results, "failures": failures}

        create_download_package(output_run_dir)
        diagnostics.run_event(
            "analysis_completed",
            completed_phases=list(results),
            failed_phases=[],
        )
        return {"run_id": run_id, "results": results, "failures": []}
    except RunCancelled:
        diagnostics.run_event(
            "analysis_cancelled",
            completed_phases=list(results),
            failed_phases=[failure["phase"] for failure in failures],
        )
        raise
    finally:
        diagnostics.stop()
