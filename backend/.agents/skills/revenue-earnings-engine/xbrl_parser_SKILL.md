---
name: xbrl-parser-SKILL.md
description: SEC XBRL data parsing
---

## Skill 1: SEC XBRL Data Parsing (`skill_xbrl_parser`)
**Objective:** Correctly extract annual financial figures while avoiding duplicate or quarterly overlaps.
**Instructions:**
1.  **Locate Concept:** Navigate the JSON to `facts.us-gaap.[Target_Tag]`. 
2.  **Filter by Form & Frame:** Look inside the `units.USD` (or `units.shares`) array. 
    *   *Rule:* ONLY select objects where `form` equals `"10-K"`.
    *   *Rule:* To get annual data, prefer objects that have a `frame` attribute like `"CY2022"` or `"CY2023"`. 
    *   *Rule:* If multiple entries exist for the same `frame` and `form`, select the one with the latest `filed` date.
3.  **Handle Missing Tags:** US GAAP tags vary by industry. If the primary tag is missing, fall back to the secondary tags listed in subsequent skills.
