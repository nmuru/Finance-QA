"""Deterministic financial-source intelligence for SEC Company Facts JSON.

This module is intentionally small for the financial-analysis smoke test. It does not
treat the downloaded JSON as a software repository. It extracts auditable facts about
the company, the reporting period covered, and the financial concepts available.

The same boundary can later be extended to additional uploaded files or a user-supplied
file location without changing the semantic-research/agent contract.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class RepositoryIntelligence:
    """Compatibility name retained for the existing orchestration."""

    schema_version: str
    root: str
    file_count: int
    files: list[str]
    cik: str
    entity_name: str
    fact_taxonomies: list[str]
    fact_count: int
    concept_names: list[str]
    fiscal_years: list[int]
    annual_periods: list[dict[str, Any]]
    latest_fiscal_year: int | None
    earliest_fiscal_year: int | None
    json_structure: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def _annual_periods(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect a compact set of annual 10-K reporting periods."""
    periods: dict[tuple[int, str], dict[str, Any]] = {}

    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, dict):
            continue
        for concept_name, concept in concepts.items():
            units = concept.get("units", {}) if isinstance(concept, dict) else {}
            for unit_name, observations in units.items():
                if not isinstance(observations, list):
                    continue
                for observation in observations:
                    if not isinstance(observation, dict):
                        continue
                    if observation.get("form") != "10-K":
                        continue
                    fy = observation.get("fy")
                    end = observation.get("end")
                    if not isinstance(fy, int) or not end:
                        continue
                    key = (fy, str(end))
                    record = periods.setdefault(
                        key,
                        {"fiscal_year": fy, "period_end": str(end), "forms": set()},
                    )
                    record["forms"].add("10-K")

    result = []
    for record in sorted(periods.values(), key=lambda item: (item["fiscal_year"], item["period_end"])):
        result.append(
            {
                "fiscal_year": record["fiscal_year"],
                "period_end": record["period_end"],
                "forms": sorted(record["forms"]),
            }
        )
    return result


def collect_repository_intelligence(repository: Path) -> RepositoryIntelligence:
    root = repository.resolve()
    source = root / "companyfacts.json"
    if not source.is_file():
        raise ValueError(f"SEC Company Facts file not found: {source}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid SEC Company Facts JSON: {exc}") from exc

    facts = payload.get("facts") or {}
    fact_taxonomies = sorted(str(key) for key in facts.keys())
    concept_names = sorted(
        f"{taxonomy}.{concept}"
        for taxonomy, concepts in facts.items()
        if isinstance(concepts, dict)
        for concept in concepts.keys()
    )
    annual_periods = _annual_periods(facts)
    fiscal_years = sorted({int(item["fiscal_year"]) for item in annual_periods})
    json_structure = {
        "format": "SEC Company Facts JSON",
        "root_keys": sorted(str(key) for key in payload.keys()),
        "facts_path": "/facts",
        "facts_shape": "/facts/<taxonomy>/<concept>/units/<unit>/[observations]",
        "taxonomies": fact_taxonomies,
        "concept_count": len(concept_names),
        "observation_access": "Use bounded JSON tools; do not load the entire resource into agent context.",
    }

    return RepositoryIntelligence(
        schema_version="financial-0.1",
        root=str(root),
        file_count=1,
        files=["companyfacts.json"],
        cik=str(payload.get("cik", "")),
        entity_name=str(payload.get("entityName", "Unknown company")),
        fact_taxonomies=fact_taxonomies,
        fact_count=len(concept_names),
        concept_names=concept_names[:500],
        fiscal_years=fiscal_years,
        annual_periods=annual_periods,
        latest_fiscal_year=max(fiscal_years) if fiscal_years else None,
        earliest_fiscal_year=min(fiscal_years) if fiscal_years else None,
        json_structure=json_structure,
    )
