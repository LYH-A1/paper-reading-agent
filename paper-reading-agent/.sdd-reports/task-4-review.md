# Task 4 Review: Prompt Templates

**Reviewer**: Claude Agent  
**Date**: 2026-06-17  
**Commit**: 8f556b7  
**File**: `paper-reading-agent/backend/llm/prompts.py`

## Checklist

| # | Check | Status |
|---|-------|--------|
| 1 | File exists at `paper-reading-agent/backend/llm/prompts.py` and imports without errors | PASS |
| 2 | All 9 constants present: REPORT_PROMPT, CLASSIFY_PROMPT, PLANNER_PROMPTS, ANSWER_PROMPTS, OBSERVE_PROMPT, REVIEWER_PROMPT, REWRITE_PROMPT, FOLLOWUP_PROMPT, KEYWORD_RULES | PASS |
| 3 | CLASSIFY_PROMPT uses `{query}` and `{title}` placeholders | PASS |
| 4 | REVIEWER_PROMPT mentions R0/R1/R2 evidence levels with required fields | PASS |
| 5 | KEYWORD_RULES dict has all 4 intents (summary, qa, compare, recommend) with keyword lists | PASS |
| 6 | PLANNER_PROMPTS and ANSWER_PROMPTS are dicts with all 4 intent keys | PASS |

## Details

**Check 1**: File loads successfully via `from backend.llm.prompts import *`.

**Check 2**: All 9 constants are defined at module scope.

**Check 3**: CLASSIFY_PROMPT (lines 18-30) contains both `{query}` on line 29 and `{title}` on line 30.

**Check 4**: REVIEWER_PROMPT (lines 78-112) defines R0 (must have page + quote + section_heading, char_start + char_end), R1 (must have source_title + source_url), and R2 (must have reasoning + based_on_evidence_ids). The `evidence_list` entry schema includes all required fields: `evidence_id`, `claim`, `level`, `sentence_index`, `char_start`, `char_end`, `page`, `quote`, `section_heading`, `confidence`.

**Check 5**: KEYWORD_RULES (lines 125-130) is a dict with exactly 4 keys: `summary`, `qa`, `compare`, `recommend`. Each key maps to a list of strings (Chinese + English keywords).

**Check 6**: PLANNER_PROMPTS (lines 32-37) is a dict with all 4 keys. ANSWER_PROMPTS (lines 39-61) is a dict with all 4 keys.

## Verdict

**APPROVED** -- All 6 checks pass. The file is complete and structurally correct.
