---
name: margin-analysis-SKILL.md
description: Gross, operating, and net margin analysis
---

## Skill 3: Margin Evolution (`skill_margin_calc`)
**Objective:** Determine if the company is gaining or losing operating leverage.
**Instructions:**
1.  **Extract Data:** 
    *   *Gross Profit Tags:* `GrossProfit`. (If missing, calculate: `Revenues` - `CostOfGoodsAndServicesSold` or `CostOfRevenue`).
    *   *Operating Income Tags:* `OperatingIncomeLoss`.
    *   *Net Income Tags:* `NetIncomeLoss`.
2.  **Calculate Margins (per year):**
    *   *Gross Margin %:* `(Gross Profit / Revenue) * 100`
    *   *Operating Margin %:* `(Operating Income / Revenue) * 100`
    *   *Net Margin %:* `(Net Income / Revenue) * 100`
3.  **Trend Analysis Logic:** 
    *   Compare the Latest Year margins to the Year T-3 margins.
    *   If Operating Margin % increases while Gross Margin % decreases, note: "Operating leverage achieved through SG&A efficiency despite core cost pressures."
    *   If Operating Margin % is negative, classify as "Currently unprofitable at the operating level."

