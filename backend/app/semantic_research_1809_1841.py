"""LLM-assisted semantic summaries for financial  analysis.

The deterministic intelligence modules remain the auditable source of repository facts.
This module adds bounded reasoning passes that summarize those supplied facts. The
summary model may read or search the already-cloned repository only when the supplied
facts are insufficient for a specific point; source access is an escape hatch, not the
primary discovery mechanism.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from openai import AsyncOpenAI

from .repository_intelligence import RepositoryIntelligence

logger = logging.getLogger(__name__)

RESEARCH_VERSION = "5"
MAX_RESEARCH_INPUT_CHARS = 120_000
MAX_PHASE_INPUT_CHARS = 100_000
MAX_REASONING_FALLBACK_CHARS = 60_000
MAX_TOOL_ROUNDS = 2
MAX_TOOL_RESULT_CHARS = 20_000
MAX_COMPLETION_TOKENS = 6_000


def _provider_base_url(provider: str) -> str:
    name = provider.strip().lower()
    if name == "openrouter":
        return "https://openrouter.ai/api/v1"
    if name == "openai":
        return "https://api.openai.com/v1"
    raise ValueError(f"Unsupported provider '{provider}'. Supported providers are: openrouter, openai")


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[deterministic intelligence truncated for the research pass]"


def _repository_research_input(intelligence: RepositoryIntelligence) -> str:
    sections = [
        "REPOSITORY INTELLIGENCE SCHEMA: " + intelligence.schema_version,
        f"FILES CONSIDERED: {intelligence.file_count}",
        "LANGUAGES: " + str(intelligence.languages),
        "TECHNOLOGIES: " + ", ".join(intelligence.technologies),
        "PACKAGE SCRIPTS: " + str(intelligence.package_scripts),
        "DEPENDENCIES: " + str(intelligence.dependencies),
        "DEV DEPENDENCIES: " + str(intelligence.dev_dependencies),
        "ENVIRONMENT VARIABLES: " + ", ".join(intelligence.env_variables),
        "ENTRY POINTS:\n" + "\n".join(f"- {x}" for x in intelligence.entry_points[:100]),
        "API ROUTES:\n" + "\n".join(f"- {x}" for x in intelligence.api_routes[:180]),
        "PAGES:\n" + "\n".join(f"- {x}" for x in intelligence.page_files[:180]),
        "DOCUMENTATION EXCERPTS:\n" + "\n\n".join(f"### {path}\n{excerpt}" for path, excerpt in list(intelligence.documentation_excerpts.items())[:12]),
        "INTEGRATION FILES:\n" + "\n".join(f"- {x}" for x in intelligence.integration_files[:120]),
        "CONFIG/CI FILES:\n" + "\n".join(f"- {x}" for x in (intelligence.config_files + intelligence.ci_files)[:160]),
        "SOURCE FILES AND SYMBOLS:\n" + "\n".join(
            f"- {item.path} [{item.language or 'unknown'}] imports={item.imports[:12]} exports={item.exports[:12]} symbols={item.symbols}"
            for item in intelligence.source_files[:500]
        ),
        "LOCAL DEPENDENCY EDGES:\n" + "\n".join(
            f"- {edge.source} -> {edge.target}" + (f" ({edge.imported_as})" if edge.imported_as else "")
            for edge in intelligence.dependency_edges[:300]
        ),
        "PARSE SUMMARY: " + str(intelligence.parse_summary),
    ]
    return _clip("\n\n".join(sections), MAX_RESEARCH_INPUT_CHARS)


REPOSITORY_RESEARCH_PROMPT = """You summarize repository facts that have already been extracted by the program.

The repository was already scanned before this request. The supplied REPOSITORY INTELLIGENCE is the primary source material for this task. You also have limited read-only access to the already-cloned repository through two tools: read_file and search_repository. Use those tools only as an escape hatch when a specific important claim cannot be understood from the supplied intelligence. Never use them for repository-wide discovery or enumeration.

Your task is to interpret the supplied facts and produce a compact narrative summary that helps downstream phases understand the repository.

Do not act like a coding agent. Do not create a research plan. Do not decide which files should be opened next. Do not enumerate repository files or generate broad search queries. Do not describe an investigation process.

Use file paths only when they directly support an important statement. A path is evidence for a statement; it is not an item to investigate. If you use a tool, state the resulting fact rather than narrating the tool use.

Summarize only what can reasonably be inferred from the supplied information:
1. Repository identity and likely product/domain
2. Strongly supported business/domain concepts
3. Likely users, actors, and system boundaries
4. Major capabilities and representative workflows visible in the supplied evidence
5. Important entities, state, and relationships suggested by the supplied evidence
6. External systems/integrations and their apparent roles
7. Important implementation characteristics relevant across financial analysis phases
8. Ambiguities, contradictions, or areas where the supplied evidence is insufficient

Rules:
- Target 700-1,200 words. Never exceed 1,500 words.
- Do not list files simply because they appear in the input.
- Do not repeat a fact or path across multiple sections.
- Do not write "need to verify" repeatedly.
- Do not invent product intent that is not supported by the supplied evidence.
- Clearly distinguish strong evidence from reasonable inference.
- When many paths show the same pattern, state the pattern and cite one or two representative paths.
- If a source read is needed, read only the smallest relevant file or search for one precise term.
- Begin directly with the repository summary. Do not discuss these instructions or your reasoning process.

Remember: your objective is to produce the summary brief from the supplied deterministic intelligence. Do not let internal reasoning exhaust the available completion budget without completing the brief; prioritize producing a useful finished summary.

The output is a summary of the supplied repository intelligence. It is not a replacement for source verification by downstream agents."""


PHASE_RESEARCH_PROMPTS = {
    "business-purpose": """Summarize the product/domain purpose, likely users, value, major capabilities, and system boundaries already suggested by the supplied repository intelligence. Focus on what the supplied evidence says. Use repository tools only for a specific unresolved point that materially affects the summary; do not create a discovery plan.""",
    "scope": """Summarize the evidence-based scope of the system represented by the repository: what appears to be part of the system, the major application areas and boundaries, included capabilities and components, external systems that are dependencies rather than part of the system, and important areas that appear outside the repository's scope. Distinguish clearly between observed repository evidence and reasonable inference. Use repository tools only for a specific ambiguity that materially affects the scope summary. Do not create a discovery plan or list files to inspect.""",
    "business-requirements": """Summarize the business behavior that is already visible in the supplied repository intelligence: actors, goals, capabilities, workflows, validation, business rules, state changes, permissions, outcomes, dependencies, and notable exceptions. Convert implementation signals into cautious, technology-agnostic interpretations. Use repository tools only for a specific ambiguity that materially affects the summary. Do not propose files to inspect or a research plan.""",
    "features": """Summarize the user-visible capabilities and representative end-to-end workflows already suggested by the supplied repository intelligence. Mention representative evidence paths only when they support an important capability. Use repository tools only for a specific missing source detail; do not create an exploration plan.""",
    "software-requirements": """Summarize externally observable behavior already indicated by the supplied repository intelligence: inputs, outputs, APIs, pages, operations, validation, state changes, error handling, and integration behavior. Use repository tools only for a specific missing source detail. Do not plan further repository inspection.""",
    "technology-architecture": """Summarize the runtime structure, component relationships, data flow, integrations, configuration, state, caching, and dependency relationships already indicated by the supplied repository intelligence. Distinguish evidence from inference. Use repository tools only for a specific ambiguity, not for broad discovery.""",
    "design-pattern": """Summarize recurring structural patterns, responsibilities, abstractions, dependency direction, and integration mechanisms that can already be inferred from the supplied repository intelligence. Treat names and paths as evidence, not as a reason to enumerate or inspect files. Use repository tools only for a specific missing detail.""",
    "high-level-design": """Summarize the logical subsystems, responsibilities, interactions, major data/control flows, and external boundaries already suggested by the supplied repository intelligence. Use repository tools only for a specific ambiguity that materially affects the summary. Do not produce a list of files to inspect.""",
    "low-level-design": """Summarize important modules, functions, contracts, control flow, data transformations, validation, state handling, and implementation relationships already visible in the supplied repository intelligence. Focus on representative evidence rather than cataloguing symbols. Use repository tools only for a specific missing detail.""",
    "implementation-detail": """Summarize important implementation mechanisms, algorithms, functions/classes, dependencies, configuration, error handling, and operational details already visible in the supplied repository intelligence. Use repository tools only for a specific missing source detail. Do not create a discovery or verification plan.""",
    "testing-harness": """Summarize the test strategy, test organization, fixtures, mocks, integration boundaries, coverage signals, and behavior verification already visible in the supplied repository intelligence. Use repository tools only for a specific missing detail. Do not produce a list of tests or files to inspect next.""",
    "future-directions": """Summarize evidence-backed gaps, explicit TODO/debt markers, incomplete areas, missing tests, brittle boundaries, and dependency/configuration risks already visible in the supplied repository intelligence. Separate observed gaps from speculation. Use repository tools only for a specific missing detail.""",
}


def _phase_prompt(phase: str) -> str:
    return PHASE_RESEARCH_PROMPTS.get(
        phase,
        "Summarize the most important evidence, behavior, relationships, and uncertainties relevant to this financial analysis phase using only the supplied repository intelligence. Use repository tools only for a specific ambiguity. Do not propose further investigation.",
    )


def _extract_message_content(response: Any) -> str | None:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    if message is None:
        return None
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        joined = "".join(parts).strip()
        if joined:
            return joined
    output_text = getattr(message, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    return None


def _extract_reasoning_fallback(response: Any) -> str | None:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    if message is None:
        return None
    for name in ("reasoning", "reasoning_content", "analysis"):
        value = getattr(message, name, None)
        if isinstance(value, str) and value.strip():
            return _clip(value.strip(), MAX_REASONING_FALLBACK_CHARS)
    return None


def _response_diagnostics(response: Any) -> dict[str, Any]:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return {"choices": 0}
    message = getattr(choices[0], "message", None)
    return {
        "choices": len(choices),
        "finish_reason": getattr(choices[0], "finish_reason", None),
        "message_content_type": type(getattr(message, "content", None)).__name__ if message else None,
        "has_tool_calls": bool(message and getattr(message, "tool_calls", None)),
        "has_reasoning": bool(message and any(getattr(message, name, None) for name in ("reasoning", "reasoning_content", "analysis"))),
    }


def _repository_tools(repository: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = repository.resolve()

    def safe_path(relative_path: str) -> Path:
        path = (root / relative_path).resolve()
        if path != root and root not in path.parents:
            raise ValueError("Path must remain inside the repository")
        return path

    def read_file(path: str, max_chars: int = 30000) -> str:
        target = safe_path(path)
        if not target.is_file():
            return "File does not exist or is not a regular file."
        try:
            return target.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except OSError as exc:
            return f"Could not read file: {exc}"

    def search_repository(query: str, max_results: int = 50) -> str:
        if not query.strip():
            return "Query must not be empty."
        matches: list[str] = []
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

    schemas = [
        {"type": "function", "function": {"name": "read_file", "description": "Read one specific repository file when the supplied intelligence is insufficient for an important claim.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1, "maximum": 30000}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "search_repository", "description": "Search repository text for one precise term when the supplied intelligence is insufficient for an important claim. Do not use for broad discovery.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["query"]}}},
    ]
    return schemas, {"read_file": read_file, "search_repository": search_repository}


async def _one_shot_chat(*, provider: str, model: str, api_key: str, system_prompt: str, user_prompt: str, repository: Path) -> str:
    client = AsyncOpenAI(base_url=_provider_base_url(provider), api_key=api_key.strip())
    tools, handlers = _repository_tools(repository)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    tool_rounds = 0
    try:
        while True:
            tool_choice = "auto" if tool_rounds < MAX_TOOL_ROUNDS else "none"
            try:
                response = await client.chat.completions.create(model=model.strip(), messages=messages, temperature=0.1, tools=tools, tool_choice=tool_choice, max_tokens=MAX_COMPLETION_TOKENS)
            except Exception as exc:
                logger.exception("SEMANTIC_RESEARCH provider request failed model=%s provider=%s tool_round=%d tool_choice=%s input_chars=%d error_type=%s error=%s", model, provider, tool_rounds, tool_choice, sum(len(str(message.get("content") or "")) for message in messages), type(exc).__name__, exc)
                raise

            diagnostics = _response_diagnostics(response)
            logger.info("SEMANTIC_RESEARCH response model=%s provider=%s tool_round=%d diagnostics=%s", model, provider, tool_rounds, diagnostics)
            choices = getattr(response, "choices", None) or []
            message = getattr(choices[0], "message", None) if choices else None
            tool_calls = getattr(message, "tool_calls", None) or [] if message else []
            if tool_calls and tool_rounds < MAX_TOOL_ROUNDS:
                messages.append({"role": "assistant", "content": getattr(message, "content", None), "tool_calls": [{"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}} for call in tool_calls]})
                for call in tool_calls[:2]:
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                        result = handlers[call.function.name](**arguments)
                    except Exception as exc:
                        result = f"Tool call failed: {exc}"
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": _clip(str(result), MAX_TOOL_RESULT_CHARS)})
                tool_rounds += 1
                continue

            content = _extract_message_content(response)
            if content:
                return content
            reasoning = _extract_reasoning_fallback(response)
            if reasoning:
                logger.warning("SEMANTIC_RESEARCH model returned reasoning without answer; failing closed")
                raise RuntimeError(f"Research LLM returned reasoning but no final answer. finish_reason={diagnostics.get('finish_reason')}; reasoning_chars={len(reasoning)}")
            raise RuntimeError("Research LLM returned an empty response. " + f"finish_reason={diagnostics.get('finish_reason')}; response_diagnostics={json.dumps(diagnostics, default=str)}")
    finally:
        await client.close()


def run_repository_research(*, intelligence: RepositoryIntelligence, repository: Path, provider: str, model: str, api_key: str) -> str:
    if not api_key or not api_key.strip():
        raise ValueError("An API key is required for repository research")
    return asyncio.run(_one_shot_chat(repository=repository, provider=provider, model=model, api_key=api_key, system_prompt=REPOSITORY_RESEARCH_PROMPT, user_prompt=_repository_research_input(intelligence)))


def run_phase_research(*, phase: str, phase_intelligence: str, repository_research: str, repository: Path, provider: str, model: str, api_key: str) -> str:
    if not api_key or not api_key.strip():
        raise ValueError(f"An API key is required for phase research '{phase}'")
    user_prompt = _clip(
        "REPOSITORY SUMMARY:\n" + repository_research
        + "\n\nDETERMINISTIC PHASE INTELLIGENCE:\n" + phase_intelligence
        + "\n\nPHASE FOCUS:\n" + _phase_prompt(phase)
        + "\n\nProduce a semantic research brief for the downstream phase agent. Synthesize the strongest useful findings from the supplied intelligence, including important relationships, representative evidence paths, and material uncertainties where relevant. Do not invent unsupported details or turn this into a repository-wide enumeration. Remember: your objective is to produce a summary brief based on the supplied deterministic intelligence; do not let reasoning exhaust the available completion budget without completing the brief. Prioritize a useful finished brief over additional internal analysis.",
        MAX_PHASE_INPUT_CHARS,
    )
    system_prompt = """You are a semantic research assistant inside an financial analysis pipeline.

The downstream phase agent is responsible for the actual financial analysis and final documentation. Your role is to provide a strong research brief that helps that agent understand the repository and reach source evidence efficiently. You are not required to perform the final phase analysis, but you should synthesize the supplied evidence thoroughly enough to be genuinely useful.

The program has already supplied a repository-level semantic summary and deterministic phase intelligence. Use those as the primary source material. You have limited read-only access to the already-cloned repository through read_file and search_repository when a specific important point cannot be understood from the supplied material.

Produce a coherent, evidence-grounded semantic brief. Cover the strongest findings relevant to the phase, representative source locations when useful, important relationships and behaviors, and material ambiguities or uncertainties. Do not enumerate the repository, create a broad research plan, or narrate your reasoning. Distinguish observed evidence from reasonable inference.

If the supplied evidence is sufficient, do not use repository tools. If a specific ambiguity materially affects the brief, use a precise file read or search rather than broad discovery.

Remember: your objective is to complete a useful summary brief from the supplied deterministic intelligence. Do not spend the available completion budget on internal reasoning without producing the final brief. If time or token budget is constrained, finish the brief with the strongest supported findings rather than continuing analysis."""
    return asyncio.run(_one_shot_chat(repository=repository, provider=provider, model=model, api_key=api_key, system_prompt=system_prompt, user_prompt=user_prompt))


def write_research_artifact(path: Path, *, kind: str, phase: Optional[str], content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [f"# {kind.title()} Research Brief", "", f"Research schema: {RESEARCH_VERSION}", f"Phase: {phase or 'repository-wide'}", "", "> This is an upstream reasoning artifact. It is not authoritative evidence or final financial analysis documentation. Material claims must be verified against repository source.", ""]
    path.write_text("\n".join(header) + content + "\n", encoding="utf-8")
