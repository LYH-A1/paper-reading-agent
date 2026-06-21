# Task 4: Frontend Citation Confidence Indicators

**Status:** Complete

## Files Modified

- `frontend/src/components/Evidence/EvidenceBadge.tsx` — Added `ConfidenceIcon` helper component that renders a colored icon (green checkmark, yellow warning, or red X) based on confidence level, displayed next to the evidence level badge.
- `frontend/src/components/Evidence/EvidencePopover.tsx` — Added verification warning section that appears when `confidence < 0.5`, showing an orange warning banner with the truncated quote and "unverified citation" message.

## Test Results

- **Test files:** 13 passed
- **Tests:** 60 passed
- **Duration:** 9.96s

## Commit

```
feat: add citation confidence indicators to evidence UI

Green checkmark (>0.7), yellow warning (0.3-0.7), red X (<0.3).
Verification warnings shown in EvidencePopover for low-confidence
citations. Complements backend citation verification (Task 3).
```
