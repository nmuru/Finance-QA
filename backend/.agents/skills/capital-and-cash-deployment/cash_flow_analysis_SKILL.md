---
name: cash-flow-analysis
description: Operating cash flow, capital expenditure, and free cash flow analysis
---

## Skill: Cash Flow Analysis
**Objective:** Establish the company's historical cash-generation profile.

**Instructions:**
1. Retrieve the annual cash flow statement with `get_financial_statements`.
2. Identify operating cash flow and capital expenditures using the reported statement rows.
3. When both are available, calculate free cash flow as operating cash flow minus capital expenditures.
4. Calculate year-over-year changes for operating cash flow and free cash flow when the data supports the calculation.
5. Preserve the source sign convention. If capital expenditures are already reported as a negative cash flow, use the economically consistent subtraction/addition needed to avoid double-negating the amount.
6. State when a component is unavailable rather than substituting an unsupported proxy.
