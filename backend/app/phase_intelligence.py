"""Compact deterministic financial evidence manifest for phase agents."""
from __future__ import annotations

import json
from typing import Any


def build_phase_intelligence(financial_intelligence: str, phase: str) -> str:
    """Return only the metadata needed to orient an agent before tool retrieval.

    Actual financial rows remain outside the LLM context and are retrieved through
    get_financial_statements at runtime.
    """
    try:
        payload: dict[str, Any] = json.loads(financial_intelligence)
    except (TypeError, ValueError, json.JSONDecodeError):
        return f"""FINANCIAL EVIDENCE MANIFEST: {phase}
Source: SEC via EdgarTools
Financial data is available through the get_financial_statements tool.
"""

    company = payload.get("company") or {}
    historical = payload.get("historical") or {}
    annual = payload.get("annual") or {}
    statements = []
    for key, label in (
        ("income_statement", "income statement"),
        ("balance_sheet", "balance sheet"),
        ("cash_flow_statement", "cash flow statement"),
    ):
        selected = historical.get(key) or annual.get(key) or {}
        if selected.get("available"):
            statements.append(label)

    period_count = historical.get("periods_requested") or 3
    return "\n".join([
        f"FINANCIAL EVIDENCE MANIFEST: {phase}",
        f"Company: {company.get('name') or 'unknown'}",
        f"SEC CIK: {company.get('cik') or 'unknown'}",
        f"Ticker: {company.get('ticker') or 'not supplied'}",
        f"Source: {payload.get('source') or 'SEC via EdgarTools'}",
        f"Annual historical periods available: {period_count}",
        f"Available statements: {', '.join(statements) or 'none detected'}",
        "Financial statement rows are intentionally outside the model context.",
        "Retrieve actual values with get_financial_statements before making quantitative claims.",
        "Use structured JSON tools only for targeted XBRL evidence not covered by the statement tool.",
    ])


def collect_phase_intelligence(financial_intelligence: str, phase: str) -> str:
    return build_phase_intelligence(financial_intelligence, phase)
