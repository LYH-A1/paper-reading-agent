# Task 4: Prompt Templates — Report

## Status
- [x] `paper-reading-agent/backend/llm/prompts.py` created
- [x] Python import verified (`from backend.llm.prompts import ...`)
- [x] Committed

## Commits
- `8f556b7` feat: add prompt templates for all 5 intents + reviewer + rewrite

## Files
- `paper-reading-agent/backend/llm/prompts.py` (new, 130 lines)

## Constants Defined

| Constant | Purpose |
|---|---|
| `REPORT_PROMPT` | Full paper → JSON report (title, authors, contributions, etc.) |
| `CLASSIFY_PROMPT` | Classify user query into summary/qa/compare/recommend intent |
| `PLANNER_PROMPTS` | Per-intent plan generation prompts (summary, qa, compare, recommend) |
| `ANSWER_PROMPTS` | Per-intent answer generation prompts with reference format rules |
| `OBSERVE_PROMPT` | Evaluate plan validity and answer sufficiency |
| `REVIEWER_PROMPT` | Evidence annotation (R0/R1/R2) and quality scoring (0-10) |
| `REWRITE_PROMPT` | Rewrite answer based on reviewer deductions |
| `FOLLOWUP_PROMPT` | Generate 3 follow-up questions |
| `KEYWORD_RULES` | Intent keyword mappings (bilingual: Chinese + English) |

## Concerns
- None. All prompts are module-level string constants as required; no LLM calls are made in this module.
