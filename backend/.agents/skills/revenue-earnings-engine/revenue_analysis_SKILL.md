---
name: revenue-analysis-SKILL.md
description: Revenue growth and CAGR analysis
---

## Skill 2: Top-Line Analysis (`skill_revenue_calc`)
**Objective:** Calculate historical revenue growth and Compound Annual Growth Rate (CAGR).
**Instructions:**
1.  **Extract Data:** Use `skill_xbrl_parser` to extract values for the last 3-5 years for the following tags (try in order until data is found):
    *   `Revenues`
    *   `SalesRevenueNet`
    *   `SalesRevenueGoodsNet`
    *   `RevenuesNetOfInterestExpense` (for financial firms)
2.  **Calculate YoY Growth:** 
    *   *Formula:* `((Current Year Revenue / Previous Year Revenue) - 1) * 100`
    *   *Execution:* Calculate this for each consecutive year pair.
3.  **Calculate 3-Year CAGR:**
    *   *Formula:* `((Latest Year Revenue / Year T-3 Revenue) ^ (1/3) - 1) * 100`
4.  **Analysis Logic:** If YoY growth is decelerating (e.g., 20% -> 15% -> 8%), explicitly state: "Revenue growth is decelerating." If CAGR > 10%, classify as "High Growth."
