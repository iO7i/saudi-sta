# Seed Saudi Speech Set

`SEED_HUMAN_EVAL` is a private, local, human-reviewed evaluation set. It is not
called representative of Saudi Arabia and it is never used as a training set in
Slice 02.

## Collection protocol

1. Record or upload a short clip in the local Workbench. The audio stays in the
   ignored local runtime directory.
2. In **Seed speech set**, enter the human-reviewed verbatim transcript and the
   expected safe proposal. This is the reference; a model never generates it.
3. Add critical spans with an error label where useful. The reviewer/session fields
   provide provenance without requiring a personal name.
4. Run only `SEED_HUMAN_EVAL` in a real tournament. Authored smoke fixtures are
   intentionally a different dataset and leaderboard.

Target: 20–30 clips from the local recorder, spread across Arabic, Saudi-colloquial
phrasing, Arabic-English code switching, corrections, negation, names, reminders,
notes, list operations, spoken numbers, and ambiguity.

## Recommended first cases

| Case | Expected behaviour | Critical spans to consider |
|---|---|---|
| `ذكرني الساعة سبعة... لا، ثمانية.` | Final time is 8, not 7 | `ثمانية` / `CORRECTION_ERROR` |
| `جهّز لي رسالة لأحمد بس لا ترسلها.` | Draft only; no send action exists | `لا ترسلها` / `NEGATION_ERROR`, name span |
| `حط milk وبيض وprotein bars في المقاضي.` | Preserve the three items | `milk`, `protein bars` / `CODE_SWITCH_ERROR` |
| `ذكرني بكرة بعد المغرب.` | Clarify rather than invent a clock time | relative-time span |
| `أضفها للقائمة الثانية.` | Clarify if no list is established | ambiguous-reference span |
| Spoken numbers | Keep `ثلاثة ونص`, `خمسة وعشرين`, `3.5`, embedded English numbers, and identifier-like digits exact | `NUMBER_ERROR` |
| `لا تسوي تذكير، بس لخص الكلام.` | Summary only; no reminder proposal | `لا تسوي تذكير` / `NEGATION_ERROR` |

## Labels

Speech labels: `SUBSTITUTION`, `DELETION`, `INSERTION`, `NUMBER_ERROR`,
`NAME_ERROR`, `CODE_SWITCH_ERROR`, `NEGATION_ERROR`, `CORRECTION_ERROR`.

Action labels: `WRONG_INTENT`, `WRONG_TOOL`, `WRONG_ARGUMENT`,
`MISSING_ARGUMENT`, `INVENTED_ARGUMENT`, `IGNORED_CORRECTION`,
`IGNORED_NEGATION`, `UNNECESSARY_CLARIFICATION`, `MISSED_CLARIFICATION`.

The evaluation UI records these as review-facing diagnostics. They do not trigger
automatic escalation, pseudo-label promotion, or training.
