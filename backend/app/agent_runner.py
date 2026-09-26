"""OpenAI Agents SDK phase runner for repository reverse engineering."""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from agents import Agent, Runner, RunHooks, function_tool, set_tracing_export_api_key
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from .config import settings
from .edgar_financials import EdgarFinancialsError, collect_financial_statements
from .run_control import RunCancelled, RunControl

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS_SOURCE = PROJECT_ROOT / ".agents" / "agents"
SKILLS_SOURCE = PROJECT_ROOT / ".agents" / "skills"
COMMON_AGENT_SOURCE = PROJECT_ROOT / ".agents" / "agent.md"

logger.info(
    "OpenAI tracing key loaded: %s",
    bool(settings.openai_api_key),
)

logger.info("PROJECT_ROOT=%s", PROJECT_ROOT)
logger.info("OPENAI_API_KEY loaded=%s", bool(settings.openai_api_key))
logger.info("Current working directory=%s", Path.cwd())

if settings.openai_api_key:
    set_tracing_export_api_key(settings.openai_api_key)
    logger.info("OpenAI Agents tracing export is enabled.")


class AgentRunnerError(RuntimeError):
    """Raised when a repository-analysis phase cannot be completed."""


def _read_common_agent_contract() -> str:
    if COMMON_AGENT_SOURCE.is_file():
        return COMMON_AGENT_SOURCE.read_text(encoding="utf-8", errors="replace")
    return ""


def _read_agent_definition(phase: str) -> str:
    if not AGENTS_SOURCE.exists():
        return ""
    candidate = AGENTS_SOURCE / f"{phase}.md"
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8", errors="replace")
    return ""


def _extract_skill_frontmatter(content: str) -> str:
    """Return only the YAML frontmatter from a skill Markdown file."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[: index + 1])
    return ""


def _discover_skill_metadata(phase: str) -> list[dict[str, str]]:
    """Discover skills by filename convention and load only their YAML frontmatter."""
    skill_dir = SKILLS_SOURCE / phase
    if not skill_dir.is_dir():
        return []

    candidates = sorted(
        path for path in skill_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".md"
        and (path.name.upper().startswith("SKILL_") or path.name.upper().endswith("_SKILL.MD"))
    )

    skills: list[dict[str, str]] = []
    for path in candidates:
        frontmatter = _extract_skill_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if not frontmatter:
            logger.warning("Skill file has no YAML frontmatter: %s", path)
            continue
        skills.append({"file": path.name, "metadata": frontmatter})
    return skills


def _format_skill_metadata(skills: list[dict[str, str]]) -> str:
    if not skills:
        return "SKILL INVENTORY\nNo convention-matching skills were discovered for this phase."
    lines = ["SKILL INVENTORY", "Only YAML frontmatter is loaded into the agent context. Skill Markdown bodies are not loaded automatically."]
    for skill in skills:
        lines.append(f"\nfile: {skill['file']}\n{skill['metadata']}")
    return "\n".join(lines)


def _resolve_skill_resources(phase: str, output_run_dir: Path) -> dict[str, Any]:
    """Discover runtime-owned resources for a phase without reading their contents."""
    skill_dir = (SKILLS_SOURCE / phase).resolve()
    resources: dict[str, Any] = {
        "root": str(skill_dir),
        "skill": "dynamic-skill-discovery",
        "artifacts": {},
        "tools": {
            "repository": ["list_files", "glob", "grep", "read_file", "search_repository"],
            "financial": ["get_financial_statements"],
            "structured_json": ["inspect_json_structure", "search_json", "read_json_value", "query_json"],
            "runtime_resources": ["list_resources", "read_resource"],
            "output_content": ["list_previous_phase_outputs", "read_previous_phase_output"],
        },
    }
    if skill_dir.is_dir():
        for resource_path in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
            relative_path = resource_path.relative_to(skill_dir).as_posix()
            if relative_path != "SKILL.md":
                resources["artifacts"][relative_path] = relative_path
    if output_run_dir.exists():
        resources["artifacts"]["output_content"] = str(output_run_dir.resolve())
    return resources


def _format_skill_resources(resources: dict[str, Any]) -> str:
    """Render runtime resource inventory and tool identifiers as agent-facing context."""
    lines = ["RUNTIME-SUPPLIED RESOURCES", f"skill: {resources.get('skill', 'SKILL.md')}"]
    artifacts = resources.get("artifacts", {})
    resource_artifacts = {name: path for name, path in artifacts.items() if name != "output_content"}
    if resource_artifacts:
        lines.append("artifacts:")
        for name, path in resource_artifacts.items():
            lines.append(f"  {name}: {path}")
    else:
        lines.append("artifacts: none")
    if "output_content" in artifacts:
        lines.append(f"output_content: {artifacts['output_content']}")
    tools_manifest = resources.get("tools", {})
    if tools_manifest:
        lines.append("tools:")
        for group, names in tools_manifest.items():
            lines.append(f"  {group}: {', '.join(names)}")
    else:
        lines.append("tools: none")
    lines.extend([
        "Runtime skill resources are relative to the supplied skill resource root; use read_resource with the supplied relative path.",
        "Use list_resources when you need to discover the complete runtime resource inventory.",
        "Use repository read_file/search/list tools for normal document resources in the workspace. JSON resources are not directly readable; use structured_json tools for bounded retrieval.",
        "Use output-content tools only for workflow artifacts from the current analysis run.",
        "Do not construct host filesystem paths or use repository tools to access runtime resources.",
    ])
    return "\n".join(lines)

def _build_tools(phase: str, repository: Path, output_run_dir: Path):
    root = repository.resolve()
    output_root = output_run_dir.resolve()
    skill_dir = (SKILLS_SOURCE / phase).resolve()

    def safe_path(relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError("Path escapes repository root.")
        return candidate

    @function_tool
    def list_resources() -> str:
        """List files available in the runtime-owned resource directory for the current phase."""
        if not skill_dir.is_dir():
            return "No runtime resources are available."
        files = sorted(
            path.relative_to(skill_dir).as_posix()
            for path in skill_dir.rglob("*")
            if path.is_file()
        )
        return "\n".join(files) if files else "No runtime resources are available."

    @function_tool
    def read_resource(path: str, max_chars: int = 30000) -> str:
        """Read a file from the runtime-owned resource directory for the current phase."""
        candidate = (skill_dir / path).resolve()
        if skill_dir != candidate and skill_dir not in candidate.parents:
            return "Invalid resource path: access outside the current phase resource directory is not allowed."
        if not candidate.is_file():
            return "Runtime resource does not exist or is not a regular file."
        try:
            bounded_chars = max(1, min(int(max_chars), 30_000))
            return candidate.read_text(encoding="utf-8", errors="replace")[:bounded_chars]
        except OSError as exc:
            return f"Could not read runtime resource: {exc}"

    @function_tool
    def list_previous_phase_outputs() -> str:
        """
        List files produced by previous SDLC phases for the current analysis run.
        Paths are relative to the current run's output-content directory.
        """
        if not output_root.exists():
            return "No previous phase outputs are available."

        if not output_root.is_dir():
            return "The current run output path is not a directory."

        files = sorted(
            path.relative_to(output_root).as_posix()
            for path in output_root.rglob("*")
            if path.is_file() and path.name != "run-state.json"
        )

        if not files:
            return "No previous phase outputs are available."

        return "\n".join(files)

    @function_tool
    def read_previous_phase_output(filename: str) -> str:
        """
        Read a specific previous-phase output file from the current analysis run.
        The filename must be one returned by list_previous_phase_outputs().
        """
        file_path = (output_root / filename).resolve()

        # Prevent path traversal outside the current run output directory.
        if output_root != file_path and output_root not in file_path.parents:
            return "Invalid filename: access outside the current run output directory is not allowed."

        if not file_path.exists():
            return f"Previous phase output not found: {filename}"

        if not file_path.is_file():
            return f"Not a file: {filename}"

        try:
            return file_path.read_text(encoding="utf-8", errors="replace")[:30_000]
        except OSError as exc:
            return f"Unable to read {filename}: {exc}"
    @function_tool
    def list_resources() -> str:
        """List files available in the current phase's runtime resource directory."""
        if not skill_dir.is_dir():
            return "No runtime resources are available."
        files = sorted(
            path.relative_to(skill_dir).as_posix()
            for path in skill_dir.rglob("*")
            if path.is_file()
        )
        return "\n".join(files) if files else "No runtime resources are available."

    @function_tool
    def read_resource(path: str, max_chars: int = 30000) -> str:
        """Read a file from the current phase's runtime resource directory."""
        resource_root = skill_dir.resolve()
        candidate = (resource_root / path).resolve()
        if resource_root != candidate and resource_root not in candidate.parents:
            return "Invalid resource path: access outside the current phase resource directory is not allowed."
        if not candidate.is_file():
            return "Runtime resource does not exist or is not a regular file."
        try:
            bounded_chars = max(1, min(int(max_chars), 30_000))
            return candidate.read_text(encoding="utf-8", errors="replace")[:bounded_chars]
        except OSError as exc:
            return f"Could not read runtime resource: {exc}"


    @function_tool
    def get_financial_statements(statement: str = "income_statement", periods: int = 5) -> str:
        """Retrieve bounded, actual SEC financial-statement rows collected by EdgarTools.

        This is the primary financial evidence tool. It reads the normalized
        financial collection created for this run and returns only the requested
        statement and recent annual periods. It does not expose the raw Company
        Facts JSON wholesale.
        """
        data_path = root / "financial-data.json"
        if not data_path.is_file():
            return "Normalized financial data is not available for this run."
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"Could not read normalized financial data: {type(exc).__name__}: {exc}"

        aliases = {
            "income_statement": "income_statement",
            "income": "income_statement",
            "profit_loss": "income_statement",
            "balance_sheet": "balance_sheet",
            "balance": "balance_sheet",
            "cash_flow": "cash_flow_statement",
            "cash_flow_statement": "cash_flow_statement",
            "cashflow": "cash_flow_statement",
        }
        key = aliases.get(statement.strip().lower())
        if not key:
            return "Unknown statement. Use income_statement, balance_sheet, or cash_flow_statement."

        periods = max(1, min(int(periods), 10))
        source = payload.get("historical") or payload.get("annual") or {}
        selected = source.get(key, {})
        if not selected.get("available"):
            return json.dumps({"available": False, "statement": key}, ensure_ascii=False)

        table = selected.get("table", "")
        rows = selected.get("rows", [])
        columns = [str(x) for x in selected.get("columns", []) if str(x).strip()]

        # The human-readable table is the primary representation. The row data
        # remains available as structured JSON for exact values when needed.
        result = {
            "source": payload.get("source", "SEC via EdgarTools"),
            "company": payload.get("company", {}),
            "statement": key,
            "periods_requested": periods,
            "columns": columns,
            "table": table,
            "rows": rows,
        }
        serialized = json.dumps(result, ensure_ascii=False)
        if len(serialized) > 40000:
            # Prefer preserving the readable table and trim structured rows.
            result["rows"] = rows[:80]
            result["truncated"] = True
            serialized = json.dumps(result, ensure_ascii=False)
        return serialized

    @function_tool
    def list_files(path: str = ".", max_entries: int = 300) -> str:
        """List repository files and directories recursively, without modifying anything."""
        target = safe_path(path)
        if not target.exists():
            return "Path does not exist."
        entries = []
        for item in target.rglob("*"):
            if ".git" in item.parts:
                continue
            entries.append(str(item.relative_to(root)))
            if len(entries) >= max_entries:
                entries.append("[truncated]")
                break
        return "\n".join(entries)

    @function_tool
    def read_file(path: str, max_chars: int = 30000) -> str:
        """Read a bounded slice of a normal workspace document.

        Structured JSON evidence should be queried with the JSON tools instead of
        requesting the entire document. The server enforces a hard response limit
        regardless of the requested max_chars.
        """
        target = safe_path(path)
        if not target.is_file():
            return "File does not exist or is not a regular file."

        hard_limit = 30_000
        bounded_chars = max(1, min(int(max_chars), hard_limit))
        try:
            if target.suffix.lower() == ".json":
                size = target.stat().st_size
                if size > hard_limit:
                    return (
                        "This JSON resource is larger than the direct-read limit. "
                        "Use inspect_json_structure, search_json, read_json_value, or query_json "
                        "to retrieve a bounded evidence slice."
                    )
            return target.read_text(encoding="utf-8", errors="replace")[:bounded_chars]
        except OSError as exc:
            return f"Could not read file: {exc}"

    def _load_json_resource(path: str) -> tuple[Path | None, Any | None, str | None]:
        """Load one workspace JSON resource without exposing it wholesale."""
        target = safe_path(path)
        if not target.is_file():
            return None, None, "JSON resource does not exist or is not a regular file."
        if target.suffix.lower() != ".json":
            return None, None, "The requested resource is not a JSON file."
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return None, None, f"Invalid JSON resource: {exc}"
        except OSError as exc:
            return None, None, f"Could not read JSON resource: {exc}"
        return target, payload, None

    def _json_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        return "string"

    def _json_pointer_get(payload: Any, pointer: str) -> Any:
        if pointer in ("", "/"):
            return payload
        current = payload
        for raw_part in pointer.strip("/").split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                if part not in current:
                    raise KeyError(part)
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                raise KeyError(part)
        return current

    @function_tool
    def inspect_json_structure(path: str = "companyfacts.json", json_pointer: str = "", max_items: int = 100) -> str:
        """Inspect the structure of a JSON resource without returning its full data.

        Returns bounded keys, array lengths, and scalar metadata. Use this first
        when the schema is unfamiliar.
        """
        _, payload, error = _load_json_resource(path)
        if error:
            return error
        try:
            value = _json_pointer_get(payload, json_pointer)
        except (KeyError, IndexError, ValueError) as exc:
            return f"JSON path not found: {json_pointer} ({exc})"

        if isinstance(value, dict):
            keys = list(value.keys())
            shown = keys[:max(1, min(int(max_items), 200))]
            suffix = " [truncated]" if len(keys) > len(shown) else ""
            return json.dumps({
                "path": json_pointer or "/",
                "type": "object",
                "key_count": len(keys),
                "keys": shown,
                "truncated": bool(suffix),
            }, ensure_ascii=False)
        if isinstance(value, list):
            return json.dumps({
                "path": json_pointer or "/",
                "type": "array",
                "length": len(value),
                "item_types": sorted({_json_type(item) for item in value[:200]}),
            }, ensure_ascii=False)
        return json.dumps({
            "path": json_pointer or "/",
            "type": _json_type(value),
            "value": value,
        }, ensure_ascii=False)

    @function_tool
    def search_json(path: str = "companyfacts.json", query: str = "", max_results: int = 50) -> str:
        """Search JSON keys and scalar values and return only small matching paths.

        This is schema-independent discovery. It never returns whole JSON objects
        or arrays and is capped server-side.
        """
        _, payload, error = _load_json_resource(path)
        if error:
            return error
        needle = query.strip().lower()
        if not needle:
            return "A non-empty JSON search query is required."

        results: list[str] = []
        hard_limit = max(1, min(int(max_results), 100))

        def walk(value: Any, pointer: str) -> None:
            if len(results) >= hard_limit:
                return
            if isinstance(value, dict):
                for key, child in value.items():
                    child_pointer = f"{pointer}/{str(key).replace('~', '~0').replace('/', '~1')}"
                    if needle in str(key).lower():
                        results.append(child_pointer)
                        if len(results) >= hard_limit:
                            return
                    walk(child, child_pointer)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{pointer}/{index}")

        walk(payload, "")
        return json.dumps({
            "query": query,
            "matches": results,
            "count": len(results),
            "truncated": len(results) >= hard_limit,
        }, ensure_ascii=False)

    @function_tool
    def read_json_value(path: str, json_pointer: str, max_chars: int = 12000) -> str:
        """Read one bounded JSON value by RFC 6901-style JSON Pointer.

        Large objects and arrays are summarized rather than returned wholesale.
        """
        _, payload, error = _load_json_resource(path)
        if error:
            return error
        try:
            value = _json_pointer_get(payload, json_pointer)
        except (KeyError, IndexError, ValueError) as exc:
            return f"JSON path not found: {json_pointer} ({exc})"

        hard_limit = 12_000
        if isinstance(value, (dict, list)):
            raw = json.dumps(value, ensure_ascii=False)
            if len(raw) > hard_limit:
                return json.dumps({
                    "path": json_pointer,
                    "type": _json_type(value),
                    "message": "Value exceeds the direct JSON value limit. Inspect structure or query a narrower path.",
                    "serialized_chars": len(raw),
                }, ensure_ascii=False)
        else:
            raw = json.dumps(value, ensure_ascii=False)

        return raw[:max(1, min(int(max_chars), hard_limit))]

    @function_tool
    def query_json(path: str, json_pointer: str = "", key: str = "", value: str = "", max_results: int = 50) -> str:
        """Query objects/arrays in a JSON resource and return bounded matching records.

        Use this for structured retrieval when the exact schema is partly known.
        Matching is performed locally; only matching records are returned.
        Results are capped by the server.
        """
        _, payload, error = _load_json_resource(path)
        if error:
            return error

        try:
            target = _json_pointer_get(payload, json_pointer)
        except (KeyError, IndexError, ValueError) as exc:
            return f"JSON path not found: {json_pointer} ({exc})"

        if not isinstance(target, (dict, list)):
            return json.dumps({"path": json_pointer, "value": target}, ensure_ascii=False)

        needle_key = key.strip().lower()
        needle_value = value.strip().lower()
        matches: list[Any] = []
        hard_limit = max(1, min(int(max_results), 50))

        candidates = target.items() if isinstance(target, dict) else enumerate(target)
        for item_key, item_value in candidates:
            if len(matches) >= hard_limit:
                break
            record_text = json.dumps(item_value, ensure_ascii=False).lower()
            key_match = not needle_key or needle_key in str(item_key).lower()
            value_match = not needle_value or needle_value in record_text
            if key_match and value_match:
                matches.append({"key": item_key, "value": item_value})

        serialized = json.dumps(matches, ensure_ascii=False)
        if len(serialized) > 30_000:
            # Keep each returned record bounded as well as the number of records.
            compact: list[Any] = []
            used = 0
            for match in matches:
                piece = json.dumps(match, ensure_ascii=False)
                if used + len(piece) + 2 > 30_000:
                    break
                compact.append(match)
                used += len(piece) + 2
            matches = compact

        return json.dumps({
            "path": json_pointer or "/",
            "matches": matches,
            "count": len(matches),
            "truncated": len(matches) >= hard_limit,
        }, ensure_ascii=False)

    @function_tool
    def search_repository(query: str, max_results: int = 100) -> str:
        """Search repository text for conditional follow-up evidence not already present in deterministic intelligence."""
        matches = []
        for item in root.rglob("*"):
            if ".git" in item.parts or not item.is_file():
                continue
            try:
                with item.open("r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if query.lower() in line.lower():
                            matches.append(f"{item.relative_to(root)}:{line_number}: {line.rstrip()}")
                            if len(matches) >= max_results:
                                return "\n".join(matches + ["[truncated]"])
            except OSError:
                continue
        return "\n".join(matches) if matches else "No matches found."
    
    @function_tool
    def glob(pattern: str, path: str = ".", max_results: int = 300) -> str:
        """Find repository files and directories whose paths match a glob pattern."""
        base = safe_path(path)
        matches = []

        for item in base.glob(pattern):
            if ".git" in item.parts:
                continue
            matches.append(str(item.relative_to(root)))
            if len(matches) >= max_results:
                matches.append("[truncated]")
                break

        return "\n".join(matches) if matches else "No matches found."
    
    @function_tool
    def grep(pattern: str, path: str = ".", max_results: int = 100) -> str:
        """Search repository file contents for a text or regular-expression pattern."""
        import re

        base = safe_path(path)
        regex = re.compile(pattern, re.IGNORECASE)
        matches = []

        for item in base.rglob("*"):
            if ".git" in item.parts or not item.is_file():
                continue

            try:
                with item.open("r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if regex.search(line):
                            matches.append(
                                f"{item.relative_to(root)}:{line_number}: {line.rstrip()}"
                            )
                            if len(matches) >= max_results:
                                return "\n".join(matches + ["[truncated]"])
            except OSError:
                continue

        return "\n".join(matches) if matches else "No matches found."

    return [
        list_files,
        glob,
        grep,
        read_file,
        search_repository,
        inspect_json_structure,
        search_json,
        read_json_value,
        query_json,
        get_financial_statements,
        list_resources,
        read_resource,
        list_previous_phase_outputs,
        read_previous_phase_output,
    ]


def _preview(value: Any, limit: int = 800) -> str:
    text = str(value).replace("\n", "\\n")
    return text[:limit] + ("...[truncated]" if len(text) > limit else "")


class AgentDiagnosticsHooks(RunHooks):
    def __init__(self, trace_id: str, phase: str):
        self.trace_id = trace_id
        self.phase = phase
        self.llm_turn = 0
        self.tool_calls = 0

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        self.llm_turn += 1
        input_chars = len(json.dumps(input_items, ensure_ascii=False, default=str))
        logger.warning(
            "AGENT_DIAG llm_start trace_id=%s phase=%s turn=%d input_items=%d input_chars=%d system_prompt_chars=%d",
            self.trace_id, self.phase, self.llm_turn, len(input_items), input_chars,
            len(system_prompt or ""),
        )

    async def on_llm_end(self, context, agent, response) -> None:
        output_items = getattr(response, "output", []) or []
        usage = getattr(context, "usage", None)
        logger.warning("AGENT_DIAG llm_end trace_id=%s phase=%s turn=%d output_items=%d usage_requests=%s", self.trace_id, self.phase, self.llm_turn, len(output_items), getattr(usage, "requests", None))

    async def on_tool_start(self, context, agent, tool) -> None:
        self.tool_calls += 1
        logger.warning("AGENT_DIAG tool_start trace_id=%s phase=%s turn=%d tool_index=%d tool=%s", self.trace_id, self.phase, self.llm_turn, self.tool_calls, getattr(tool, "name", type(tool).__name__))

    async def on_tool_end(self, context, agent, tool, result) -> None:
        logger.warning("AGENT_DIAG tool_end trace_id=%s phase=%s turn=%d tool_index=%d tool=%s result_chars=%d result_preview=%s", self.trace_id, self.phase, self.llm_turn, self.tool_calls, getattr(tool, "name", type(tool).__name__), len(str(result)), _preview(result, 1200))

    async def on_agent_end(self, context, agent, output) -> None:
        logger.warning("AGENT_DIAG agent_end trace_id=%s phase=%s turns=%d tool_calls=%d output_preview=%s", self.trace_id, self.phase, self.llm_turn, self.tool_calls, _preview(output, 1000))


async def _wait_for_cancellation(run_control: RunControl) -> None:
    while not run_control.is_cancelled():
        await asyncio.sleep(0.2)


async def _run_agent(*, phase: str, phase_name: str, repository: Path, phase_intelligence: str, model: str, api_key: str, provider: str, previous_output: Optional[str], output_run_dir: Path, run_control: Optional[RunControl] = None) -> tuple[str, str]:
    provider_name = provider.strip().lower()
    if provider_name == "openrouter":
        base_url = "https://openrouter.ai/api/v1"
    elif provider_name == "openai":
        base_url = "https://api.openai.com/v1"
    else:
        raise AgentRunnerError(f"Unsupported provider '{provider}'. Supported providers are: openrouter, openai")

    common_agent_contract = _read_common_agent_contract()
    agent_definition = _read_agent_definition(phase)
    skill_metadata = _discover_skill_metadata(phase)
    skill_metadata_context = _format_skill_metadata(skill_metadata)
    skill_resources = _resolve_skill_resources(phase, output_run_dir)
    resource_context = _format_skill_resources(skill_resources)
    handoff = ""
    if previous_output:
        handoff = "\n\nPrevious phase output is supporting context only. Verify important claims against repository evidence.\n\n" + previous_output[:20000]

    common_instructions = """You are performing an evidence-driven financial analysis phase.
Financial evidence is stored outside the model context and must be retrieved selectively.
Start with get_financial_statements for the statement(s) relevant to the phase. It returns actual SEC-reported rows collected by EdgarTools.
Use JSON tools only when the requested evidence is not available through the financial statement tool or when a specific SEC XBRL fact needs verification.
Use read_file only for non-JSON user-supplied documents.
Do not invent financial facts or values. Distinguish verified data, reasonable analytical inference, and unknowns when evidence is incomplete.
The supplied financial files are read-only. Do not modify them.
Return only complete professional Markdown financial analysis for the requested phase. Do not describe the agent, tools, prompts, intelligence collection, or execution process.
Skill resources are supplied explicitly by the runtime. Use those paths and tool identifiers instead of discovering them.

FINANCIAL ANALYSIS BUDGET
Prioritize high-value financial evidence and synthesis. When the available evidence is sufficient, stop broad exploration and produce the best-supported analysis. Never invent missing figures; state when data is unavailable or insufficient."""

    bounded_phase_intelligence = phase_intelligence
    instructions = "\n\n".join(
        part for part in [
            common_instructions,
            common_agent_contract,
            agent_definition,
            resource_context,
            skill_metadata_context,
            bounded_phase_intelligence,
            handoff,
        ] if part
    )
    client = AsyncOpenAI(base_url=base_url, api_key=api_key.strip())
    agent = Agent(name=f"Financial {phase_name}", instructions=instructions, model=OpenAIChatCompletionsModel(model=model.strip(), openai_client=client), tools=_build_tools(phase, repository, output_run_dir))
    trace_id = uuid.uuid4().hex[:12]
    hooks = AgentDiagnosticsHooks(trace_id, phase)
    started = time.perf_counter()
    logger.warning("AGENT_DIAG start trace_id=%s phase=%s model=%s provider=%s repository=%s manifest_chars=%d common_agent_contract_chars=%d agent_definition_chars=%d skill_chars=%d skill_resources=%s max_turns=%d", trace_id, phase, model, provider_name, repository, len(phase_intelligence), len(common_agent_contract), len(agent_definition), len(skill_metadata_context), json.dumps(skill_resources, sort_keys=True), settings.phase_agent_max_turns)
    try:
        if run_control and run_control.is_cancelled():
            raise RunCancelled("Analysis stopped by the user.")
        agent_task = asyncio.create_task(Runner.run(agent, "Analyze the supplied financial evidence and produce the requested financial phase analysis.", hooks=hooks, max_turns=settings.phase_agent_max_turns))
        if run_control is None:
            result = await agent_task
        else:
            cancel_task = asyncio.create_task(_wait_for_cancellation(run_control))
            done, pending = await asyncio.wait({agent_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
            if cancel_task in done and run_control.is_cancelled():
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
                raise RunCancelled("Analysis stopped by the user.")
            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass
            result = await agent_task
    except RunCancelled:
        logger.warning("AGENT_DIAG cancelled trace_id=%s phase=%s elapsed_s=%.3f turns_observed=%d tool_calls_observed=%d", trace_id, phase, time.perf_counter() - started, hooks.llm_turn, hooks.tool_calls)
        raise
    except Exception as exc:
        logger.warning("AGENT_DIAG failed trace_id=%s phase=%s elapsed_s=%.3f turns_observed=%d tool_calls_observed=%d error_type=%s error=%s", trace_id, phase, time.perf_counter() - started, hooks.llm_turn, hooks.tool_calls, type(exc).__name__, str(exc))
        raise
    output = str(result.final_output or "").strip()
    if not output:
        raise AgentRunnerError(f"OpenAI Agents SDK completed phase '{phase}' but returned no final output.")

    actual_model = model.strip()
    raw_responses = getattr(result, "raw_responses", None) or []
    for raw_response in reversed(raw_responses):
        response = getattr(raw_response, "response", raw_response)
        response_model = getattr(response, "model", None)
        if response_model:
            actual_model = str(response_model)
            break
    return output, actual_model


def run_phase_agent(phase: str, phase_name: str, repository: Path, phase_intelligence: str, previous_output: Optional[str] = None, provider: str = "openrouter", model: str = "openrouter/free", api_key: Optional[str] = None, run_control: Optional[RunControl] = None) -> tuple[str, str]:
    """Run one phase against a shared read-only repository workspace and return output plus actual model used."""
    if not api_key or not api_key.strip():
        raise AgentRunnerError(f"An API key is required for provider '{provider}'.")
    if not repository.is_dir():
        raise AgentRunnerError(f"Repository path does not exist: {repository}")
    try:
        run_id = getattr(run_control, "run_id", None) if run_control is not None else None
        if not run_id and run_control is not None:
            state_path = getattr(run_control, "state_path", None)
            if state_path:
                run_id = Path(state_path).parent.name

        if not run_id:
            raise AgentRunnerError("Could not determine the current analysis run ID for previous phase outputs.")

        output_run_dir = PROJECT_ROOT / "output-content" / str(run_id)
        return asyncio.run(
            _run_agent(
                phase=phase,
                phase_name=phase_name,
                repository=repository,
                phase_intelligence=phase_intelligence,
                model=model,
                api_key=api_key,
                provider=provider,
                previous_output=previous_output,
                output_run_dir=output_run_dir,
                run_control=run_control,
            )
        )
    except RunCancelled:
        raise
    except AgentRunnerError:
        raise
    except Exception as exc:
        logger.exception("OpenAI Agents SDK failed during phase %s", phase)
        raise AgentRunnerError(f"OpenAI Agents SDK failed during phase '{phase}': {exc}") from exc
