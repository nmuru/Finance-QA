"""
Presentation-stage renderer for reverse-engineering phase results.

The analysis stage is responsible for repository exploration and reasoning.
The rendering stage receives the complete raw output and a phase-specific
presentation template.
"""

from multiprocessing import get_context
from typing import Optional
import json
import time
import requests
from .config import settings
from .render_prompt import build_render_prompt, build_understand_prompt
from .resource_diagnostics import ResourceDiagnostics
from .run_control import RunCancelled, RunControl
from .template_loader import load_explain_phase_skill, load_phase_template

_PROVIDER_ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}


def _renderer_request_worker(endpoint: str, api_key: str, model: str, system_prompt: str, user_prompt: str, timeout: int, connection) -> None:
    try:
        payload = {"model": model, "stream": False, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
        response = requests.post(endpoint, json=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, timeout=timeout)
        connection.send({"ok": True, "status_code": response.status_code, "headers": dict(response.headers), "body": response.text})
    except Exception as exc:
        connection.send({"ok": False, "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        connection.close()


def _request_once(*, endpoint: str, api_key: str, model: str, system_prompt: str, user_prompt: str, timeout: int, run_control: Optional[RunControl]) -> dict:
    context = get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_renderer_request_worker, args=(endpoint, api_key, model, system_prompt, user_prompt, timeout, child), daemon=True)
    process.start()
    child.close()
    try:
        while True:
            if parent.poll(0.2):
                return parent.recv()
            if run_control and run_control.is_cancelled():
                process.terminate()
                process.join(timeout=2)
                raise RunCancelled("Analysis stopped by the user.")
            if not process.is_alive():
                return {"ok": False, "error_type": "RendererProcessExit", "error": "Renderer request process exited without a response."}
    finally:
        parent.close()
        if process.is_alive():
            process.join(timeout=0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)


def _render_with_openai_compatible_api(*, endpoint: str, api_key: str, model: str, system_prompt: str, user_prompt: str, timeout: int, phase: str = "", diagnostics: Optional[ResourceDiagnostics] = None, run_control: Optional[RunControl] = None) -> str:
    response_data = None
    for attempt in range(4):
        if run_control and run_control.is_cancelled():
            raise RunCancelled("Analysis stopped by the user.")
        started = time.monotonic()
        if diagnostics:
            diagnostics.run_event("renderer_started", phase=phase, model=model, attempt=attempt + 1)
        try:
            response_data = _request_once(endpoint=endpoint, api_key=api_key, model=model, system_prompt=system_prompt, user_prompt=user_prompt, timeout=timeout, run_control=run_control)
            elapsed = round(time.monotonic() - started, 3)
            if not response_data.get("ok"):
                error_type = response_data.get("error_type", "RendererRequestError")
                error = response_data.get("error", "Renderer request failed")
                if diagnostics:
                    diagnostics.run_event("renderer_failed", phase=phase, model=model, attempt=attempt + 1, elapsed_seconds=elapsed, error_type=error_type, error=error)
                raise RuntimeError(error)
            status_code = int(response_data.get("status_code", 500))
            if status_code != 429 or attempt == 3:
                if status_code >= 400:
                    raise RuntimeError(f"Renderer returned HTTP {status_code}: {response_data.get('body', '')[:500]}")
                if diagnostics:
                    diagnostics.run_event("renderer_finished", phase=phase, model=model, attempt=attempt + 1, elapsed_seconds=elapsed, status_code=status_code)
                break
            retry_after = response_data.get("headers", {}).get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2 * (2 ** attempt)
            except (TypeError, ValueError):
                delay = 2 * (2 ** attempt)
            if diagnostics:
                diagnostics.run_event("renderer_retry", phase=phase, model=model, attempt=attempt + 1, elapsed_seconds=elapsed, delay_seconds=delay, status_code=429)
            if run_control and run_control.cancel_event.wait(delay):
                raise RunCancelled("Analysis stopped by the user.")
            if not run_control:
                time.sleep(delay)
        except RunCancelled:
            if diagnostics:
                diagnostics.run_event("renderer_cancelled", phase=phase, model=model, attempt=attempt + 1, elapsed_seconds=round(time.monotonic() - started, 3))
            raise
        except Exception as exc:
            elapsed = round(time.monotonic() - started, 3)
            if diagnostics:
                diagnostics.run_event("renderer_failed", phase=phase, model=model, attempt=attempt + 1, elapsed_seconds=elapsed, error_type=type(exc).__name__, error=str(exc))
            raise
    try:
        data = json.loads(response_data["body"])
    except Exception as exc:
        if diagnostics:
            diagnostics.run_event("renderer_failed", phase=phase, model=model, error_type=type(exc).__name__, error=str(exc))
        raise RuntimeError(f"Renderer returned invalid JSON: {exc}") from exc
    rendered = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not isinstance(rendered, str) or not rendered.strip():
        if diagnostics:
            diagnostics.run_event("renderer_failed", phase=phase, model=model, error_type="EmptyResponse", error="Renderer returned an empty response")
        raise RuntimeError("Renderer returned an empty response")
    return rendered.strip()


def render_analysis(phase: str, analysis: str, template: Optional[str] = None, objective: str = "document", provider: str = "openrouter", model: Optional[str] = None, api_key: Optional[str] = None, timeout: int = 300, diagnostics: Optional[ResourceDiagnostics] = None, run_control: Optional[RunControl] = None) -> str:
    if not analysis or not analysis.strip():
        raise ValueError("analysis cannot be empty")

    objective_name = (objective or "document").strip().lower()
    if objective_name not in {"document", "understand"}:
        raise ValueError("Unsupported renderer objective: {0}. Supported objectives are: document, understand".format(objective_name))

    if objective_name == "document":
        if template is None:
            template = load_phase_template(phase)
        if not template or not template.strip():
            raise ValueError(f"template cannot be empty for phase '{phase}'")
    else:
        template = load_explain_phase_skill()

    provider_name = (provider or "openrouter").strip().lower()
    if provider_name not in _PROVIDER_ENDPOINTS:
        raise ValueError(f"Unsupported renderer provider: {provider_name}. Supported providers are: openrouter, openai")
    if not model or not model.strip():
        model = settings.agent_model
    if not api_key or not api_key.strip():
        raise ValueError(f"An API key is required for renderer provider '{provider_name}'.")

    if objective_name == "document":
        system_prompt, user_prompt = build_render_prompt(phase, analysis, template)
    else:
        system_prompt, user_prompt = build_understand_prompt(phase, analysis, template)

    return _render_with_openai_compatible_api(
        endpoint=_PROVIDER_ENDPOINTS[provider_name],
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=timeout,
        phase=phase,
        diagnostics=diagnostics,
        run_control=run_control,
    )
