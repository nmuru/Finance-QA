---
name: earnings-quality-SKILL.md
description: Earnings quality and EPS/share-count analysis
---

## Skill 4: Earnings Quality (`skill_earnings_quality`)
**Objective:** Distinguish between actual business profitability growth and financial engineering (like share buybacks).
**Instructions:**
1.  **Extract Data:**
    *   *Net Income:* `NetIncomeLoss` (from Skill 3).
    *   *Diluted EPS Tags:* `EarningsPerShareDiluted`.
    *   *Weighted Average Shares Tags:* `WeightedAverageNumberOfDilutedSharesOutstanding`.
2.  **Calculate Divergence:**
    *   Calculate 3-year YoY growth for Net Income.
    *   Calculate 3-year YoY growth for Diluted EPS.
3.  **Analysis Logic:**
    *   If EPS growth is significantly higher (>300 basis points) than Net Income growth, check the Share Outstanding trend. 
    *   If Shares Outstanding are decreasing, state: "EPS growth is being heavily subsidized by share repurchases rather than organic net income growth."
    *   Check for negative Net Income but positive EPS (an anomaly that requires flagging).
