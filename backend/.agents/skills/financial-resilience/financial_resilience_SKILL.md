 ---
name: financial-resilience-SKILL.md
description: Analyze financial resilience
---


## Skill 1: Balance Sheet XBRL Parsing (`skill_balance_sheet_parser`)
**Objective:** Correctly extract "instant" (point-in-time) balance sheet metrics, which differ fundamentally from income statement metrics.
**Instructions:**
1.  **Locate Concept:** Navigate the JSON to `facts.us-gaap.[Target_Tag]`.
2.  **Filter for Annual Point-in-Time:** Look inside the `units.USD` array.
    *   *Rule 1 (Form):* Select objects where `form` equals `"10-K"`.
    *   *Rule 2 (Instant vs Duration):* Balance sheet items do not have `start` and `end` dates. They only have an `end` date (the snapshot date).
    *   *Rule 3 (Frame):* Look for `frame` attributes ending in "I" for Instant (e.g., `"CY2022Q4I"`, which represents the instant at the end of Q4/FY 2022). If `frame` is missing, rely on the `end` date that matches the fiscal year-end date of the 10-K.
3.  **Deduplication:** If multiple entries exist for the same `end` date, select the entry with the most recent `filed` date.

---

## Skill 2: Liquidity Assessment (`skill_liquidity_assessment`)
**Objective:** Determine if the company can pay off its short-term liabilities with short-term assets.
**Instructions:**
1.  **Extract Data (Last 3 Years):**
    *   *Current Assets Tags:* `AssetsCurrent`
    *   *Current Liabilities Tags:* `LiabilitiesCurrent`
    *   *Inventory Tags:* `InventoryNet`
2.  **Calculate Current Ratio:**
    *   *Formula:* `Current Assets / Current Liabilities`
3.  **Calculate Quick Ratio (Acid Test):**
    *   *Formula:* `(Current Assets - Inventory) / Current Liabilities`
    *   *Note:* If `InventoryNet` is missing (common for software/services), assume it is 0 and Current Ratio = Quick Ratio.
4.  **Analysis Logic:**
    *   If Current Ratio is `< 1.0`, trigger a **Liquidity Warning**: "The company has more short-term debt than short-term assets, indicating potential liquidity strain."
    *   If Quick Ratio is `< 0.8`, state: "The company is highly reliant on liquidating inventory to meet short-term obligations."

---

## Skill 3: Solvency & Leverage (`skill_leverage_calc`)
**Objective:** Measure how heavily the company relies on debt financing versus equity.
**Instructions:**
1.  **Extract Data (Last 3 Years):**
    *   *Total Assets Tag:* `Assets`
    *   *Total Equity Tag:* `StockholdersEquity` (Fallback: `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`)
    *   *Short-Term Debt Tag:* `DebtCurrent` (Fallback: `ShortTermBorrowings`)
    *   *Long-Term Debt Tag:* `LongTermDebt` (Fallback: `LongTermDebtAndCapitalLeaseObligations` or `LongTermDebtNoncurrent`)
2.  **Calculate Total Debt:**
    *   *Formula:* `Short-Term Debt + Long-Term Debt`
    *   *Note:* If short-term debt is not reported, treat it as 0. Do NOT use `Liabilities` as a proxy for debt (liabilities include non-debt items like accounts payable).
3.  **Calculate Debt-to-Equity (D/E):**
    *   *Formula:* `Total Debt / Total Equity`
4.  **Calculate Debt-to-Assets:**
    *   *Formula:* `Total Debt / Total Assets`
5.  **Analysis Logic:**
    *   If D/E is `> 2.0` (excluding banks/financials), state: "The company is highly leveraged, utilizing more than twice as much debt as equity."
    *   If Total Equity is negative, trigger a **Severe Solvency Warning**: "The company has a shareholder deficit (negative equity), indicating past accumulated losses have wiped out invested capital."

---

## Skill 4: Debt Service Capacity (`skill_interest_coverage`)
**Objective:** Assess if the company generates enough operating profit to comfortably pay its interest expenses.
**Instructions:**
1.  **Extract Data (Last 3 Years):**
    *   *Operating Income Tag:* `OperatingIncomeLoss` (Note: This is a duration/period metric, use standard `CY` frame parsing from the Revenue module).
    *   *Interest Expense Tag:* `InterestExpense` (Fallback: `InterestExpenseDebt`)
2.  **Calculate Interest Coverage Ratio:**
    *   *Formula:* `Operating Income / Interest Expense`
3.  **Analysis Logic:**
    *   If Interest Expense is 0 or missing, state: "No material interest expense reported; debt servicing is currently not a risk factor."
    *   If Interest Coverage is `< 1.5x`, trigger a **Distress Warning**: "Operating income is barely covering interest payments, leaving the company highly vulnerable to earnings shocks."
    *   If Interest Coverage is `< 0`, state: "The company is generating operating losses and must rely on cash reserves or new financing to service its debt."