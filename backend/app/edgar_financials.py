"""Deterministic SEC financial-statement collection using EdgarTools.

This module contains no LLM logic and performs no financial interpretation.
It retrieves SEC-reported annual statements and serializes the actual rows
for selective agent retrieval.
"""

from __future__ import annotations

import math
import os
from typing import Any

from edgar import Company, set_identity


class EdgarFinancialsError(RuntimeError):
    """Raised when deterministic SEC financial collection cannot be completed."""


def _configure_identity() -> None:
    identity = os.getenv("EDGAR_IDENTITY", "").strip()
    if not identity:
        raise EdgarFinancialsError(
            "EDGAR_IDENTITY is required for SEC access. "
            "Set it to your name and email, for example 'Jane Doe jane@example.com'."
        )
    set_identity(identity)


def _json_value(value: Any) -> Any:
    """Convert pandas/EdgarTools values into JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except Exception:
            pass
    return str(value)


def _statement_records(statement: Any, view: str | None = "standard") -> dict[str, Any]:
    """Serialize one EdgarTools statement without passing unsupported arguments."""
    if statement is None:
        return {"available": False, "rows": [], "columns": []}

    try:
        dataframe = statement.to_dataframe() if view is None else statement.to_dataframe(view=view)
    except TypeError as exc:
        raise EdgarFinancialsError(
            f"Could not convert EdgarTools statement to a DataFrame: {exc}"
        ) from exc

    dataframe = dataframe.reset_index(drop=True)
    rows = [
        {str(key): _json_value(value) for key, value in record.items()}
        for record in dataframe.to_dict(orient="records")
    ]
    return {
        "available": True,
        "view": view,
        "columns": [str(column) for column in dataframe.columns],
        "rows": rows,
        "table": dataframe.to_string(index=False),
    }


def collect_financial_statements(
    identifier: str,
    *,
    view: str = "standard",
    historical_periods: int = 5,
) -> dict[str, Any]:
    """Collect actual annual SEC financial-statement rows.

    get_financials() supplies the normal annual statement set. When more than
    three historical periods are requested, get_facts() supplies the extended
    historical statement set. No LLM calls, ratios, or conclusions occur here.
    """
    identifier = identifier.strip()
    if not identifier:
        raise EdgarFinancialsError("A company ticker or CIK is required.")
    if view not in {"summary", "standard", "detailed"}:
        raise EdgarFinancialsError("view must be summary, standard, or detailed.")

    historical_periods = max(1, min(int(historical_periods), 20))
    _configure_identity()

    try:
        company = Company(identifier)
        financials = company.get_financials()

        result: dict[str, Any] = {
            "source": "SEC via EdgarTools",
            "identifier": identifier,
            "company": {
                "name": _json_value(getattr(company, "name", None)),
                "cik": _json_value(getattr(company, "cik", None)),
                "ticker": _json_value(getattr(company, "ticker", None)),
            },
            "annual": {
                "income_statement": _statement_records(
                    financials.income_statement(view=view), view
                ),
                "balance_sheet": _statement_records(
                    financials.balance_sheet(view=view), view
                ),
                "cash_flow_statement": _statement_records(
                    financials.cash_flow_statement(view=view), view
                ),
            },
            "historical": None,
        }

        if historical_periods > 3:
            facts = company.get_facts()
            result["historical"] = {
                "periods_requested": historical_periods,
                "income_statement": _statement_records(
                    facts.income_statement(periods=historical_periods, annual=True),
                    None,
                ),
                "balance_sheet": _statement_records(
                    facts.balance_sheet(periods=historical_periods, annual=True),
                    None,
                ),
                "cash_flow_statement": _statement_records(
                    facts.cash_flow(periods=historical_periods, annual=True),
                    None,
                ),
            }

        return result
    except EdgarFinancialsError:
        raise
    except Exception as exc:
        raise EdgarFinancialsError(
            f"EdgarTools financial collection failed for '{identifier}': "
            f"{type(exc).__name__}: {exc}"
        ) from exc
