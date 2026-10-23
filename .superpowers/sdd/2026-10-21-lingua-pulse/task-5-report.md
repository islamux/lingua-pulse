# Task 5 Report: Spaced Repetition Grading

## What I implemented
- Created `src/linguapulse/srs.py` with all required constants (`GRADES`, `DEFAULT_EASE`, `MIN_EASE`, `MAX_EASE`, `MAX_INTERVAL_DAYS`, `RELEARN_MINUTES`, `GRACE_MINUTES`) and functions:
  - `new_state(card_id, moment=None)` creates a fresh `CardState` due immediately (UTC via `models.iso`/`models.now_utc`) with `reps=0`, `ease=DEFAULT_EASE`, `notifiable=True`.
  - `apply_grade(state, grade, moment=None, zone=None)` validates grade against `GRADES` (raises `ValueError` if unknown), computes next state without mutating input, applies SM-2-like rules as specified:
    - `again`: 10 min relearn (via timedelta minutes), `ease = max(MIN_EASE, ease - 0.20)`, `reps=0`, `lapses+=1`, `notifiable=False`; due set in UTC from `moment + 10min` (plain arithmetic for the relearn step).
    - `hard` (on a card seen before): interval = max(1.0, interval*1.2), else 1.0; ease -= 0.15 (clamped to MIN_EASE); reps+=1.
    - `good`: reps==0 -> 1.0, reps==1 -> 6.0, else interval *= ease; reps+=1.
    - `easy`: reps==0 -> 3.0, reps==1 -> 8.0, else interval *= ease*1.3; ease += 0.15 (clamped to MAX_EASE); reps+=1.
  - All intervals clamped to `MAX_INTERVAL_DAYS`. For non-`again` grades, due is computed via `models.add_wall_clock(moment, interval, zone)` (preserves local time-of-day across DST). `last_graded_at` set to `models.iso(moment)`, `handled_due` cleared to `None`.

- Created `tests/test_srs.py` with all 12 tests from the brief exactly as specified.

## What I tested and test results
Focused run with verbose output (overriding addopts):
- Command: `python3 -m pytest tests/test_srs.py -v -o addopts=""`
- Result: 12 passed

Full suite:
- Command: `python3 -m pytest` (repo root; pyproject sets pythonpath and addopts)
- Result: 63 passed in 0.17s (all existing tests remain passing)

## TDD Evidence
- RED: ran `python3 -m pytest tests/test_srs.py -v` after creating the test file but before implementing `srs.py`. Collection failed with `ImportError: cannot import name 'srs' from 'linguapulse'` (module not found). This matches the expected failure in the brief.
- GREEN: created `src/linguapulse/srs.py` as specified and ran `python3 -m pytest tests/test_srs.py -v -o addopts=""` - all 12 tests PASSED.

## Files changed
- `src/linguapulse/srs.py` (new)
- `tests/test_srs.py` (new)

## Self-review findings
- Verified interface names/constants match the brief exactly (including `GRACE_MINUTES` present for future use). 
- Confirmed `apply_grade` returns a new `CardState` and does not mutate the input. Non-mutation was not covered by a test before this round (`test_grading_clears_the_handled_occurrence` only verifies the clear behavior); the new test `test_apply_grade_does_not_mutate_the_input_state` now covers it.
- Relearn step uses plain `timedelta(minutes=RELEARN_MINUTES)` (not wall-clock) as specified.
- Interval clamping and ease bounds enforced. DST test passes.
- Followed existing codebase patterns (imports, style, usage of `models` helpers).

## Any issues or concerns
None.


## Fix report (amendments after review)
- Changed `tests/test_srs.py`: added `test_apply_grade_does_not_mutate_the_input_state` (captures `due`, `interval_days`, `ease`, `reps`, `lapses`, `handled_due`, `notifiable` before call and asserts unchanged after). Tightened `test_the_interval_is_capped` from `<= srs.MAX_INTERVAL_DAYS` to `== srs.MAX_INTERVAL_DAYS` to pin the constant exactly.
- Corrected the report claim in "Self-review findings": non-mutation was not covered by a test before this round (`test_grading_clears_the_handled_occurrence` only verifies the clear behavior), and the new test now covers it.
- Covering tests run: `cd /media/islamux/Variety/Python_Projects/lingua-pulse && python3 -m pytest tests/test_srs.py -v -o addopts=""` → 14 passed in 0.03s.
- Full suite: `cd /media/islamux/Variety/Python_Projects/lingua-pulse && python3 -m pytest` → 65 passed in 0.16s.
