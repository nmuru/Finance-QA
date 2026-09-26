---
name: financial-query-guidance
description: General guidance for answering financial questions from controlled company evidence.
---

# Guidance

1. Identify the exact decision or fact the user is asking about.
2. Choose the smallest set of financial evidence needed to answer it.
3. Prefer reported SEC financial statements and actual observations over assumptions.
4. Use structured XBRL retrieval only for a specific missing or precision-sensitive fact.
5. Compare periods only when the comparison helps answer the question.
6. Explain the conclusion briefly and cite the relevant period or metric in prose.
7. Distinguish reported fact, calculation, and inference.
8. If the evidence does not support the requested conclusion, say so rather than filling the gap with speculation.

# Query Routing

For earnings, revenue, margin, or profitability questions, prioritize income-statement evidence.

For liquidity, leverage, solvency, or resilience questions, prioritize balance-sheet and cash-flow evidence.

For cash generation, capital allocation, buybacks, dividends, or investment questions, prioritize cash-flow and balance-sheet evidence.

For accounting quality, unusual movements, or anomaly questions, use statement evidence first and then targeted XBRL retrieval when necessary.

For broad questions, combine only the minimum relevant statements and synthesize them into one answer.
