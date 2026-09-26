"""CLI for deterministic SEC financial-statement collection.

Example:
    set EDGAR_IDENTITY=Jane Doe jane@example.com
    python scripts/collect_financials.py AAPL --periods 5 --view standard
"""

from __future__ import annotations

import argparse
import json

from app.edgar_financials import EdgarFinancialsError, collect_financial_statements


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect SEC financial statements through EdgarTools."
    )
    parser.add_argument("identifier", help="Company ticker or CIK, e.g. AAPL or 320193")
    parser.add_argument(
        "--periods",
        type=int,
        default=5,
        help="Number of annual historical periods to request (default: 5)",
    )
    parser.add_argument(
        "--view",
        choices=("summary", "standard", "detailed"),
        default="standard",
        help="EdgarTools statement view (default: standard)",
    )
    args = parser.parse_args()

    try:
        payload = collect_financial_statements(
            args.identifier,
            view=args.view,
            historical_periods=args.periods,
        )
    except EdgarFinancialsError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
