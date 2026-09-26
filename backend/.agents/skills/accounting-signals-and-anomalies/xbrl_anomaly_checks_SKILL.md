---
name: xbrl-anomaly-checks
description: Targeted SEC XBRL checks for filing and accounting anomalies
---

## Skill: XBRL Anomaly Checks
**Objective:** Use targeted Company Facts retrieval to validate signals that standard statements cannot fully explain.

**Instructions:**
1. Use structured JSON tools only for a specific question generated from the retrieved statements.
2. Inspect the relevant concept rather than searching the full Company Facts corpus.
3. Check observation dates, forms, units, and reported values before drawing conclusions.
4. Where useful, compare 10-K observations across years and note changes in filing timing or reported concepts.
5. Do not treat the presence or absence of an XBRL concept as evidence of an accounting issue by itself.
