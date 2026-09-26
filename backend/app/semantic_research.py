"""LLM-assisted preliminary financial research.

This stage is deliberately retained as a separate, mandatory step. Deterministic
intelligence establishes what the SEC JSON contains; this module asks the LLM to turn
that evidence into a compact, formatted preliminary brief for the downstream financial
agent. It does not pretend that a financial JSON file is a software repository.

The smoke-test version is intentionally conservative. Later versions can add richer
financial extraction, uploaded documents, user-provided file locations, and structured
financial evidence without changing the orchestration boundary.
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

RESEARCH_VERSION = "financial-0.1"
MAX_RESEARCH_INPUT_CHARS = 40_000
MAX_PHASE_INPUT_CHARS = 50_000
MAX_COMPLETION_TOKENS = 3_000


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
    return text[:limit] + "\n\n[preliminary intelligence truncated]"


def _repository_research_input(intelligence: RepositoryIntelligence) -> str:
    return _clip(
        "\n".join(
            [
                "PRELIMINARY FINANCIAL SOURCE INTELLIGENCE",
                f"Company: {intelligence.entity_name}",
                f"SEC CIK: {intelligence.cik}",
                "Source: SEC Company Facts JSON",
                f"Fiscal years: {intelligence.fiscal_years}",
                f"Annual periods: {json.dumps(intelligence.annual_periods, ensure_ascii=False)}",
                f"XBRL taxonomies: {', '.join(intelligence.fact_taxonomies)}",
                f"Financial concepts available: {intelligence.fact_count}",
                "Representative concepts:",
                *[f"- {name}" for name in intelligence.concept_names[:120]],
            ]
        ),
        MAX_RESEARCH_INPUT_CHARS,
    )


REPOSITORY_RESEARCH_PROMPT = """You are the preliminary financial research layer in a financial analysis system.

The source is SEC Company Facts JSON, not a software repository. Produce a concise, factual preliminary data brief from the supplied deterministic intelligence.

Use exactly these sections:
1. Company and Source
2. Reporting Period Covered
3. Data Available
4. Preliminary Analysis Readiness
5. Limitations

State the company name, SEC CIK, source type, fiscal-year coverage, and what kinds of XBRL financial concepts are available. Do not claim that a metric has a value merely because its concept exists. Do not invent revenue, earnings, margins, cash, debt, or other figures that were not supplied.

This is preliminary research for a downstream financial-analysis agent. Do not discuss SDLC, repositories, software architecture, technologies, users, APIs, or source-code investigation.
Return only the formatted Markdown brief."""


PHASE_RESEARCH_PROMPTS = {
    "revenue-earnings-engine": """Prepare preliminary evidence for Revenue & Earnings Engine analysis. State the company, SEC CIK, annual fiscal-year coverage, and the availability of concepts relevant to revenue, income, EPS, and margins. Do not calculate or invent values that are not present in the supplied deterministic intelligence.""",
    "financial-resilience": """Prepare preliminary evidence for Financial Resilience analysis. State the company, annual coverage, and the availability of concepts relevant to cash, debt, assets, liabilities, liquidity, and operating cash flow. Do not infer resilience from concept availability.""",
    "capital-cash-deployment": """Prepare preliminary evidence for Capital & Cash Deployment analysis. State the company, annual coverage, and the availability of concepts relevant to capital expenditure, acquisitions, dividends, repurchases, cash, and financing. Do not infer capital-allocation conclusions from concept availability.""",
    "accounting-signals-anomalies": """Prepare preliminary evidence for Accounting Signals & Anomalies analysis. State the company, annual coverage, and the availability of concepts that may support comparison of earnings, cash flow, receivables, payables, accrual-related items, and other accounting signals. Do not call anything anomalous from concept availability alone.""",
}


def _phase_prompt(phase: str) -> str:
    return PHASE_RESEARCH_PROMPTS.get(
        phase,
        "Prepare a concise preliminary financial evidence brief from the supplied deterministic intelligence.",
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
    return None


async def _one_shot_chat(
    *,
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    client = AsyncOpenAI(base_url=_provider_base_url(provider), api_key=api_key.strip())
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = await client.chat.completions.create(
            model=model.strip(),
            messages=messages,
            temperature=0.1,
            tool_choice="none",
            max_tokens=MAX_COMPLETION_TOKENS,
        )
        content = _extract_message_content(response)
        if content:
            return content
        raise RuntimeError("Financial research LLM returned an empty response")
    except Exception as exc:
        logger.exception(
            "FINANCIAL_RESEARCH request failed model=%s provider=%s input_chars=%d error_type=%s error=%s",
            model,
            provider,
            sum(len(str(message.get("content") or "")) for message in messages),
            type(exc).__name__,
            exc,
        )
        raise
    finally:
        await client.close()


def run_repository_research(
    *,
    intelligence: RepositoryIntelligence,
    repository: Path,
    provider: str,
    model: str,
    api_key: str,
) -> str:
    if not api_key or not api_key.strip():
        raise ValueError("An API key is required for financial preliminary research")
    return asyncio.run(
        _one_shot_chat(
            provider=provider,
            model=model,
            api_key=api_key,
            system_prompt=REPOSITORY_RESEARCH_PROMPT,
            user_prompt=_repository_research_input(intelligence),
        )
    )


def run_phase_research(
    *,
    phase: str,
    phase_intelligence: str,
    repository_research: str,
    repository: Path | None = None,
    provider: str,
    model: str,
    api_key: str,
) -> str:
    if not api_key or not api_key.strip():
        raise ValueError(f"An API key is required for financial phase research '{phase}'")

    user_prompt = _clip(
        "PRELIMINARY COMPANY RESEARCH:\n"
        + repository_research
        + "\n\nPHASE DETERMINISTIC INTELLIGENCE:\n"
        + phase_intelligence
        + "\n\nPHASE FOCUS:\n"
        + _phase_prompt(phase)
        + "\n\nReturn the preliminary financial evidence in a compact Markdown format. Do not invent values or conclusions.",
        MAX_PHASE_INPUT_CHARS,
    )

    system_prompt = """You are the preliminary phase-research layer of a financial analysis system.

The source is SEC Company Facts JSON and related controlled financial files. Your job is to turn the supplied deterministic facts and upstream preliminary research into a concise, structured evidence brief for a downstream financial-analysis agent.

Do not discuss SDLC, software repositories, source-code architecture, technologies, APIs, or repository investigation. Do not invent figures. Distinguish data availability from actual metric values.

Return only the formatted preliminary financial research brief."""
    return asyncio.run(
        _one_shot_chat(
            provider=provider,
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    )


def write_research_artifact(path: Path, *, kind: str, phase: Optional[str], content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    title = "Financial Preliminary Research" if kind == "repository" else "Financial Phase Preliminary Research"
    header = [
        f"# {title}",
        "",
        f"Research schema: {RESEARCH_VERSION}",
        f"Phase: {phase or 'company-wide'}",
        "",
        "> Preliminary financial evidence for downstream analysis. It is not a final financial conclusion.",
        "",
    ]
    path.write_text("\n".join(header) + content + "\n", encoding="utf-8")
