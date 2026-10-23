# Repeat reminders every 10 minutes — design

## Intent

A card that is due and still ungraded must keep reminding the user every 10
minutes, without an end, until the card is graded. The cycle survives a reboot:
when the service comes back, an overdue ungraded card notifies immediately and
then every 10 minutes again.

This replaces the original policy ("one notification per due moment, never
replay a backlog") at the user's explicit request. It is a deliberate change to
`plan.md`, not a bug fix.

## Goals

- One grouped notification at the due moment, then one every 10 minutes while
  at least one notifiable card is due and ungraded.
- No end: no repeat cap, no quiet hours, no per-day limit.
- Resumption after a reboot or service restart without losing the cycle.
- Grading a card ends its repeats and clears its reminder clock.
- Still no polling: the daemon sleeps to the exact next reminder (or due) time.
- Backwards-compatible state files, no migration step.

## Non-goals

- No snooze, acknowledgement or "mark as read" command.
- No configurable cadence or quiet hours.
- No change to the SRS intervals, the grouping format or the CLI.
- No GUI, tray icon or extra dependency.

## Constraints

- Standard library only; Python 3.11+.
- The scheduler lock and the SIGHUP nudge keep working as today.
- Display times stay local; stored times stay UTC.
- `again` stays silent: a relearn card is not notifiable, it never nags, it is
  reviewed in the terminal.
- When notifications are disabled, nothing is sent and no reminder wakeups are
  scheduled.

## Approaches

**A. Persisted reminder clock (chosen).** One optional timestamp per card state,
`last_reminded_at`. The next reminder is `last_reminded_at + 10 minutes`; before
the first reminder it is the due time. The daemon sleeps to the minimum of the
next due time and the next reminder time.

**B. Derive the slot from the due time, nothing persisted.** `due + 10k`
generates the reminders. Rejected: every service restart would notify again
immediately, and there is no way to remember where the cycle was.

**C. A separate reminder queue file.** Materialized pending reminders. Rejected:
a second source of truth that must be kept in sync with every grade, for no
benefit over a field in the state file.

## Behaviour

1. **Eligibility.** A card is reminded at moment `t` when its state is
   `notifiable`, its due time is `<= t`, and it was never reminded
   (`last_reminded_at is None`) or its last reminder is at least 10 minutes old.
2. **Delivery.** One notification lists every eligible card, exactly as the
   grouped notification works today. Every card in it gets
   `last_reminded_at = t`.
3. **Failures.** A failed `notify-send` still advances the clock, so the next
   attempt is the next 10-minute slot; this prevents a tight failure loop. The
   failure log and its rate limiting are unchanged.
4. **Next wakeup.** The scheduler wakes at the earliest of: a card's first due
   time, a card's next reminder time, and (when nothing else is scheduled) the
   hourly rescan. A reminder time already in the past wakes the loop
   immediately.
5. **Boot and restart.** `last_reminded_at` is persisted. After a reboot, the
   service starts with the user session; any card whose slot has passed
   notifies immediately, then the cadence continues. A restart two minutes
   after a notification waits the remaining eight minutes.
6. **Grading.** Grading builds a fresh state, so `last_reminded_at` is empty and
   the new due time starts a new cycle. Grading also wakes the daemon as today.
7. **Relearn.** `notifiable=False` after `again`; such a card is never part of a
   reminder, no matter how overdue it is.
8. **Notifications disabled.** No notification is sent and no reminder wakeup is
   scheduled; due cards are still recorded once so re-enabling does not produce
   a burst of stale reminders.

## Data model

`models.CardState` replaces `handled_due` with
`last_reminded_at: str | None`, an ISO 8601 UTC timestamp. The field is optional
in JSON and is ignored when absent, so existing files load unchanged. Old
`handled_due` keys are simply not read.

Consequence: the first start after upgrading has no reminder clock, so an
overdue ungraded card notifies immediately. That is the intended boot behaviour,
not a regression.

No `state.json` version bump is needed; the change is additive at the document
level and tolerant at the record level.

## Code touchpoints

- `models.py`: the new field, `to_dict`/`from_dict`, state validation.
- `scheduler.py`: eligibility, grouping without the 15-minute grace or backlog
  skipping, and `next_wakeup` including reminder times.
- `srs.py`: drop `GRACE_MINUTES`; grading already returns a fresh state.
- `daemon.py`: mark `last_reminded_at` instead of `handled_due`, pass the
  notification setting into the wakeup computation, keep the failure log.
- `diagnostics.py`: follow the `next_wakeup` signature (the doctor keeps showing
  the next wakeup).
- `cli.py`: unchanged; `status` keeps showing due cards and the next due time.

## Documentation and spec

- `plan.md` §2: allow the repeat; keep the "no tight loop" and rate limiting.
- `plan.md` §9: replace the 15-minute late rule and the backlog policy with the
  repeat rule and the boot behaviour.
- `plan.md` §8 acceptance criteria: replace "once per due card" and the missed
  reminder item.
- `README.md`: rewrite the scheduler and notification bullets; the README copy
  inside the plan's Task 15 block must stay byte-identical, so both are updated
  together.
- No version bump.

## Testing

- **Scheduler:** first reminder at due; second only after 10 minutes; grouping
  of cards with different due times; `notifiable=False` never reminds;
  `next_wakeup` returns a past reminder immediately and the next future slot
  otherwise.
- **State:** round-trip of `last_reminded_at`, old files without it, old files
  with `handled_due`.
- **Daemon:** a fake notifier and a patched clock; reminders at due, +10, +20;
  immediate reminder after a restart when the slot passed; no reminder within
  the 10 minutes; failure advances the clock and is logged once; disabled
  notifications send nothing and schedule no reminder wakeups.
- **End to end:** scratch home, one overdue card, three loop iterations with a
  patched clock, three notifications.
- **Regression:** `doctor`, `status`, grading, install/uninstall and the rest of
  the suite stay green.

## Risks

- **Volume.** Six notifications per hour per ungraded due card, grouped into
  one. Accepted by the user.
- **Overnight nagging.** No quiet hours by design.
- **Spec drift.** `plan.md` is edited in the same change; the README/plan copy
  is kept identical by a test in the final check.
