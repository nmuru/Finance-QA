"""Cancellation-aware SEC Company Facts download.

The source acquisition layer resolves a company name/ticker to its SEC CIK,
constructs the SEC Company Facts URL, and downloads the JSON into the same
workspace shape consumed by the existing analysis pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .run_control import RunCancelled, RunControl

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_USER_AGENT = "Financial-Dossier/1.0 contact@example.com"


def _check_cancelled(run_control: RunControl | None) -> None:
    if run_control and run_control.is_cancelled():
        raise RunCancelled("Analysis stopped by the user.")


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _resolve_cik(company_name: str, run_control: RunControl | None = None) -> str:
    _check_cancelled(run_control)
    query = _normalize(company_name)
    if not query:
        raise ValueError("company_name cannot be empty")

    headers = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
            response = client.get(SEC_TICKERS_URL)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not retrieve the SEC company ticker directory: {exc}") from exc

    _check_cancelled(run_control)

    try:
        companies = response.json()
    except ValueError as exc:
        raise RuntimeError("The SEC company ticker directory returned invalid JSON.") from exc

    exact_matches: list[tuple[str, str]] = []
    partial_matches: list[tuple[str, str]] = []
    for item in companies.values():
        name = str(item.get("title", "")).strip()
        ticker = str(item.get("ticker", "")).strip()
        cik = str(item.get("cik_str", "")).strip()
        if not name or not cik:
            continue
        normalized = _normalize(name)
        if normalized == query or ticker.lower() == query:
            exact_matches.append((name, cik))
        elif query in normalized:
            partial_matches.append((name, cik))

    matches = exact_matches or partial_matches
    if not matches:
        raise ValueError(f"Could not resolve '{company_name}' to an SEC company. Enter the company name or ticker as listed by the SEC.")
    if len(matches) > 1 and not exact_matches:
        names = ", ".join(name for name, _ in matches[:5])
        raise ValueError(f"'{company_name}' matched multiple SEC companies: {names}. Use a more specific company name or ticker.")

    return matches[0][1].zfill(10)


def download_company_facts(
    company_name: str,
    workspace: Path,
    run_control: RunControl | None = None,
) -> Path:
    cik = _resolve_cik(company_name, run_control=run_control)
    facts_url = SEC_COMPANY_FACTS_URL.format(cik=cik)
    repository = workspace / "target-repository"
    repository.mkdir(parents=True, exist_ok=True)
    facts_path = repository / "companyfacts.json"

    _check_cancelled(run_control)
    headers = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            response = client.get(facts_url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not download SEC Company Facts for '{company_name}': {exc}") from exc

    _check_cancelled(run_control)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("The SEC Company Facts endpoint returned invalid JSON.") from exc

    facts_path.write_text(json.dumps(payload), encoding="utf-8")
    return repository
