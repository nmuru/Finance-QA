# SDLC Dossier

ReverseEngineer-SDLC turns a GitHub repository into a progressive software-engineering dossier across 11 SDLC phases. The frontend submits selected phases to the backend, which clones the repository once, builds deterministic repository intelligence, performs semantic research, then runs the selected phase agents and renders their Markdown output.

## V1 scope

The current version is intentionally a practical first release. It supports public GitHub repositories, explicit phase selection, progressive streaming of completed phases, rerunning selected phases with the same `work_id`, and OpenRouter/OpenAI providers through the OpenAI Agents SDK.

The backend currently accepts a maximum repository size of 500 MB by default. Phase-agent execution is bounded to 15 turns by default. `phases_per_batch` defaults to 1 and parallel batch execution is the default mode. These limits are configuration values and can be changed through the backend settings, but larger repositories or larger execution budgets increase runtime and model usage.

An analysis performs more model work than the number of final dossier phases alone. There is one repository-level semantic research request, one phase-level semantic research request per selected phase, one phase-agent run per selected phase, and a separate rendering request for each completed phase. Actual token consumption and cost depend on repository size, selected phases, model/provider behavior, retries, and provider pricing or free-tier limits.

## Providers and model input

V1 intentionally exposes only the providers implemented by the backend: OpenRouter and OpenAI. The frontend should not advertise providers that the backend cannot route. The model field is passed through to the selected provider. There is no automatic model fallback in this V1 release. A rate limit, unavailable model, authentication failure, or provider error is surfaced as an analysis failure rather than silently switching to a different model.

## Run control and refresh resilience

A running analysis is independent of the browser tab. The workspace stores the `work_id` and lightweight run metadata in browser local storage; API keys are not stored. On refresh, the frontend reconnects to the backend status endpoint for that `work_id`, recovers completed phase artifacts, and resumes the same progressive-results view rather than returning to the initial setup screen.

The workspace includes a **Stop analysis** control. It cancels the selected analysis run only; it does not stop the FastAPI web server or other users' work. Stop requests prevent subsequent phases from starting and propagate cancellation into active phase-agent and renderer requests. Completed phase results remain available and the user can return to the main page. If a browser is closed after a stop request, the backend still finishes cancellation independently.

The progressive-results state remains the primary UI: completed phases stay readable while remaining phases continue, including the `10 of 11 phases have completed` case. Refresh recovery and stopping are additive to that experience.

## Output retention and runtime mode

Run diagnostics and generated phase artifacts are written under `output-content/{work_id}`. The generic `runtime_mode` setting controls their lifecycle and defaults to `evaluation` so V1 evaluation data is retained.

- `evaluation` — retain per-run output for diagnostics, evaluation, and troubleshooting.
- `production` — allow an explicit UI close/cleanup request to remove that run's output. If the run is still active, the backend cancels it first and removes the folder after cancellation completes.

Set `RUNTIME_MODE=production` in the backend environment when production retention behavior is desired. Browser refresh does not trigger cleanup; cleanup is scoped to the specific `work_id`. The browser does not provide a reliable signal that distinguishes closing a tab/window from refreshing it, so cleanup should be initiated by an explicit UI close action rather than by `pagehide`/`beforeunload` alone.

## Rate limits and failures

The analysis endpoint is an event stream. Backend validation and execution errors are returned as an `analysis_failed` event so the frontend can display a useful message instead of waiting indefinitely. Renderer requests retry HTTP 429 responses with bounded backoff before reporting failure.

This is a V1 demo/evaluation application and not every edge case has been exhaustively tested. If a phase run encounters an unexpected failure or repository-access error, do not treat the existing completed work as lost: return to the main setup page and rerun the affected phase, or start a new browser tab/workspace. Completed phase artifacts should remain available in the workspace and can be downloaded while later phases are still running.

When a run fails after some phases have completed, completed phase results remain available in the current workspace. Select a completed phase to inspect it, or use the setup screen to explicitly select a phase again and rerun it. A rerun replaces that phase's `agent-output.md` and `raw.md` artifacts for the same `work_id`.

## Mermaid diagrams

Phase documents may contain fenced `mermaid` code blocks. The frontend renders these diagrams client-side with Mermaid. When Mermaid cannot parse a diagram, the UI shows the source instead of leaving the result blank. This is intended to make diagram failures diagnosable while preserving the underlying documentation.

## Demo

The Vercel Commerce example is pre-generated and stored under `frontend/public/vercel-demo/`. It is documentation only and does not consume API credits when viewed. Real analyses use the backend pipeline and the API credentials supplied with the request.

## Security and workspace model

GitHub repositories are cloned into a temporary read-only analysis workspace for a run and are removed when that run finishes. Phase agents receive repository tools that restrict paths to the cloned repository and expose file listing, file reads, and text search without write operations. API keys are supplied per request and are not persisted by the frontend.

## Diagnostics

Resource diagnostics are enabled in the current diagnostics baseline. The backend records runtime samples and phase lifecycle events as JSONL under the run's output directory. Agent diagnostics also record phase trace identifiers, model/provider names, observed agent turns, tool-call counts, and timing information in backend logs. Renderer diagnostics now record renderer start, completion, retry, failure, cancellation, attempt number, model, phase, and elapsed seconds without logging prompts or generated content.

This information is intended to support engineering diagnostics and performance investigation. It is not presented as a claim that the application can reconstruct every provider-side billing or execution metric.

## Local development

Start the backend from `backend/` with the project's normal Python environment and start the frontend from `frontend/` with the package manager used by the repository. The frontend currently expects the backend at `http://localhost:8000`.

Before using the application, provide a provider, model, API key, GitHub repository URL, and one or more SDLC phases. For repeat runs, keep the returned `run_id` and explicitly select phases to rerun within that workspace.

## Run locally

You can simulate the application on your Windows desktop by cloning this repository and running `start.bat`. The script creates the Python virtual environment and installs the backend dependencies from `backend/requirements.txt`, installs the frontend npm dependencies, and starts the FastAPI backend and Next.js frontend.

Before running `start.bat`, make sure the following are installed:

- **Git**
- **Python 3.11+** with `python` available on PATH
- **Node.js 20.9+** with `npm` available on PATH

For the Financial Dossier, SEC access also requires an **EDGAR identity** (your name and email address). Set it in the terminal before starting the application, for example:

```bat
set EDGAR_IDENTITY=Your Name your.email@example.com
```

You also need an API key for the AI provider used by the application. The easiest way to try the UI without running an analysis is to use the pre-generated INFY and IBM demo data. To run a live financial analysis, enter your provider, model, and API key in the application.

After cloning:

```bat
git clone https://github.com/nmuru/Financial-Dossier.git
cd Financial-Dossier
set EDGAR_IDENTITY=Your Name your.email@example.com
start.bat
```

The frontend runs on the local Next.js development server, normally at **http://localhost:3000**. The backend runs on **http://localhost:8000**.

**Windows note:** the current `start.bat` contains machine-specific paths from the author's development environment. If those paths do not match your machine, use the commands below instead of `start.bat`:

```bat
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\frontend
npm install
```

Then start the backend in one terminal:

```bat
cd backend
set EDGAR_IDENTITY=Your Name your.email@example.com
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

and the frontend in another:

```bat
cd frontend
npm run dev
```

