# Repeat Reminders Every 10 Minutes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A due card notifies at its due time and then every 10 minutes, without a limit, until it is graded, and the cadence survives a reboot.

**Architecture:** Each `CardState` gets a persisted `last_reminded_at` timestamp. The scheduler computes a card's next reminder as `max(due, last_reminded_at + 10 minutes)`; the daemon sleeps to the earliest reminder or due time, sends one grouped notification and records the reminder time. The old 15-minute grace window and backlog skipping are removed.

**Tech Stack:** Python 3.11+, standard library only, pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-repeat-reminders-design.md`

## Global Constraints

- Standard library only at runtime; no new dependency.
- Python 3.11 or newer.
- Store timestamps in UTC; display them in local time.
- No periodic polling loop. Sleep to the exact next event.
- One scheduler only, enforced by the existing lock; SIGHUP still recomputes the wakeup.
- State files written by the previous version must load without a migration step.
- Grouping format and CLI stay unchanged. No version bump.
- Work on a fresh branch `feat-repeat-reminders` created from `main`; include the design doc in the first commit.

## Review Focus

- **Exactly ten minutes.** 9:59 must not remind; 10:00 must. Pinned by `test_a_reminder_is_not_repeated_inside_the_ten_minute_slot` and `test_a_reminder_repeats_at_the_exact_ten_minute_boundary`.
- **Restart with a stale clock.** A restart after 11+ minutes must notify immediately; a restart at 2 minutes must wait 8. Pinned by `test_next_wakeup_counts_the_remaining_minutes_of_the_reminder_slot` and `test_a_card_is_notified_again_after_ten_minutes`.
- **Grade race while sending.** A grade saved during `notify-send` must keep its new due/reps; the old reminder mark must not swallow the new schedule. Pinned by `test_a_grade_saved_while_sending_survives_the_marks`.
- **Failed send.** The failure must advance the clock so the next attempt is 10 minutes later, never a tight loop. Pinned by `test_a_failing_notification_records_the_reminder_time` and `test_a_failed_notification_is_not_retried_inside_the_slot`.
- **Notifications disabled.** Nothing is sent and no 10-minute wakeups are scheduled; re-enabling resumes. Pinned by `test_disabled_notifications_record_the_reminder_time` and `test_next_wakeup_ignores_reminders_when_notifications_are_disabled`.

---

### Task 1: The repeat clock end to end

**Files:**
- Modify: `src/linguapulse/models.py:138-181`
- Modify: `src/linguapulse/srs.py:9-20`
- Modify: `src/linguapulse/scheduler.py`
- Modify: `src/linguapulse/daemon.py:22-30,145-235,280-324`
- Modify: `src/linguapulse/diagnostics.py:212-214`
- Test: `tests/test_models.py`, `tests/test_srs.py`, `tests/test_scheduler.py`, `tests/test_daemon.py`, `tests/test_cli.py`, `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `models.CardState.last_reminded_at: str | None` (replaces `handled_due`).
  - `srs.REMINDER_MINUTES = 10`; `srs.GRACE_MINUTES` is removed.
  - `scheduler.reminder_time(card: models.Card, state: models.CardState | None, moment: datetime) -> datetime | None`.
  - `scheduler.pending_occurrences(cards, states, moment) -> list[Occurrence]` — now driven by `reminder_time`.
  - `scheduler.plan_reminder(pending: Iterable[Occurrence]) -> tuple[Occurrence, ...]` — returns every pending occurrence sorted by due time; empty tuple when none.
  - `scheduler.next_wakeup(cards, states, moment, notify_enabled: bool = True) -> datetime | None`.
  - `daemon.DeliveryReport(delivered, notified, message, reminded)`.
  - `daemon._mark_reminded(states, occurrences, moment) -> tuple[tuple[str, str], ...]`.

- [ ] **Step 0: Create the work branch**

```bash
git checkout main
git pull --ff-only
git checkout -b feat-repeat-reminders
```

Expected: `git status` shows the untracked design and plan documents carried onto the new branch.

- [ ] **Step 1: Write the failing state and grading tests**

In `tests/test_models.py`, replace the `handled_due` keyword in `test_card_state_round_trip` and `test_save_and_load_states_round_trip` with `last_reminded_at="2026-10-21T09:00:00+00:00"`. Add:

```python
def test_an_old_state_file_ignores_handled_due():
    state = models.CardState.from_dict(
        {
            "card_id": "hello",
            "due": "2026-10-22T09:00:00+00:00",
            "handled_due": "2026-10-21T09:00:00+00:00",
        }
    )
    assert state.last_reminded_at is None
```

In `tests/test_srs.py`, rename `test_grading_clears_the_handled_occurrence` to `test_grading_clears_the_reminder_clock`, replace the `handled_due` assignment with `first.last_reminded_at = "2026-10-21T09:00:00+00:00"`, and assert `second.last_reminded_at is None`. In `test_apply_grade_does_not_mutate_the_input_state`, replace both `state.handled_due` entries with `state.last_reminded_at`.

- [ ] **Step 2: Run the state tests to verify they fail**

Run: `python3 -m pytest tests/test_models.py tests/test_srs.py -q`
Expected: FAIL — `last_reminded_at` is not a field, `handled_due` still exists.

- [ ] **Step 3: Change the state model and the shared constant**

In `src/linguapulse/models.py`, replace `handled_due: str | None = None` with `last_reminded_at: str | None = None`, and in `to_dict`/`from_dict` replace the `"handled_due"` key and lookup with `"last_reminded_at"`. In `src/linguapulse/srs.py`, add `REMINDER_MINUTES = 10` next to `RELEARN_MINUTES`, delete `GRACE_MINUTES`, and delete the `handled_due=None` keyword from the `CardState(...)` built at the end of `apply_grade` (a fresh state starts with `last_reminded_at` unset).

- [ ] **Step 4: Run the state tests to verify they pass**

Run: `python3 -m pytest tests/test_models.py tests/test_srs.py -q`
Expected: PASS.

- [ ] **Step 5: Rewrite the scheduler tests**

Replace the body of `tests/test_scheduler.py` with the following cases, keeping `make_card`, `state_for`, `NOW`, `test_a_broken_due_falls_back_to_the_creation_time` and `test_the_due_iso_of_an_occurrence_round_trips`:

```python
def test_a_due_card_is_pending():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    assert [o.card.id for o in scheduler.pending_occurrences(cards, states, NOW)] == ["hello"]


def test_a_card_that_is_not_due_is_not_pending():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_reminder_is_not_repeated_inside_the_ten_minute_slot():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:55:00+00:00"
        )
    }
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_reminder_repeats_at_the_exact_ten_minute_boundary():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:50:00+00:00"
        )
    }
    assert [o.card.id for o in scheduler.pending_occurrences(cards, states, NOW)] == ["hello"]


def test_a_broken_reminder_clock_is_treated_as_never_reminded():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="not a timestamp"
        )
    }
    assert [o.card.id for o in scheduler.pending_occurrences(cards, states, NOW)] == ["hello"]


def test_a_relearn_card_is_never_pending():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:55:00+00:00", notifiable=False)}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_card_without_a_state_has_no_scheduled_review():
    cards = {"hello": make_card()}
    assert scheduler.pending_occurrences(cards, {}, NOW) == []
    assert scheduler.next_wakeup(cards, {}, NOW) is None


def test_next_wakeup_returns_the_soonest_future_due():
    cards = {"hello": make_card(), "world": make_card()}
    states = {
        "hello": state_for("hello", "2026-10-22T09:00:00+00:00"),
        "world": state_for("world", "2026-10-21T12:00:00+00:00"),
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_next_wakeup_counts_the_remaining_minutes_of_the_reminder_slot():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:55:00+00:00"
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 9, 5, tzinfo=timezone.utc)


def test_a_reminder_slot_in_the_past_is_returned_for_an_immediate_wakeup():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:20:00+00:00"
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 8, 30, tzinfo=timezone.utc)


def test_a_card_that_was_never_reminded_wakes_at_its_past_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-20T09:00:00+00:00")}
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def test_next_wakeup_ignores_reminders_when_notifications_are_disabled():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T10:00:00+00:00", last_reminded_at="2026-10-21T08:55:00+00:00"
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW, notify_enabled=False) == datetime(
        2026, 10, 21, 10, 0, tzinfo=timezone.utc
    )


def test_next_wakeup_without_notifications_is_none_for_an_overdue_card():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    assert scheduler.next_wakeup(cards, states, NOW, notify_enabled=False) is None


def test_plan_reminder_groups_every_pending_card():
    cards = {"old": make_card("old"), "late": make_card("late")}
    states = {
        "old": state_for("old", "2026-10-21T06:00:00+00:00"),
        "late": state_for("late", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    group = scheduler.plan_reminder(pending)
    assert [o.card.id for o in group] == ["old", "late"]


def test_an_empty_backlog_plans_nothing():
    assert scheduler.plan_reminder([]) == ()
```

- [ ] **Step 6: Run the scheduler tests to verify they fail**

Run: `python3 -m pytest tests/test_scheduler.py -q`
Expected: FAIL — `reminder_time` is missing and the old grace/skip logic is still in place.

- [ ] **Step 7: Implement the scheduler functions**

In `src/linguapulse/scheduler.py`, import `timedelta` and `REMINDER_MINUTES`, delete the `Reminder` dataclass, and replace everything from `_scheduled_review` to the end of the file with:

```python
def reminder_time(
    card: models.Card,
    state: models.CardState | None,
    moment: datetime,
) -> datetime | None:
    """Return the time of the next reminder for one card, if it has one.

    A card without a state has no scheduled review: it is never due, it never
    wakes the scheduler up and it is never reminded. The relearn step of an
    "again" grade is not notifiable, so it is not reminded either.
    """
    if state is None or not state.notifiable:
        return None
    due = occurrence_due(card, state, moment)
    last = models.safe_parse_iso(state.last_reminded_at)
    if last is None:
        return due
    return max(due, last + timedelta(minutes=REMINDER_MINUTES))


def pending_occurrences(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[Occurrence]:
    """Return the cards that are due and whose reminder slot has passed."""
    pending: list[Occurrence] = []
    for card_id in sorted(cards):
        card = cards[card_id]
        state = states.get(card_id)
        slot = reminder_time(card, state, moment)
        if slot is None or slot > moment:
            continue
        pending.append(
            Occurrence(card=card, due=occurrence_due(card, state, moment), state=state)
        )
    return pending


def next_wakeup(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
    notify_enabled: bool = True,
) -> datetime | None:
    """Return the exact time of the next event worth waking up for."""
    candidates: list[datetime] = []
    for card_id in sorted(cards):
        card = cards[card_id]
        state = states.get(card_id)
        if notify_enabled:
            slot = reminder_time(card, state, moment)
            if slot is not None:
                candidates.append(slot)
        elif state is not None and state.notifiable:
            due = occurrence_due(card, state, moment)
            if due > moment:
                candidates.append(due)
    return min(candidates) if candidates else None


def plan_reminder(pending: Iterable[Occurrence]) -> tuple[Occurrence, ...]:
    """Group every pending occurrence into one reminder, oldest first."""
    return tuple(sorted(pending, key=lambda occurrence: occurrence.due))
```

- [ ] **Step 8: Run the scheduler tests to verify they pass**

Run: `python3 -m pytest tests/test_scheduler.py -q`
Expected: PASS.

- [ ] **Step 9: Rewrite the daemon tests**

In `tests/test_daemon.py`:
- Replace `test_the_delivered_occurrence_is_marked_as_handled` with the new `test_the_delivered_card_records_the_reminder_time` below.
- In `test_a_failing_notification_is_reported`, change `handled_due is not None` to `last_reminded_at is not None`.
- Replace `test_a_stale_backlog_is_skipped` with the overdue test below.
- In the remaining `handled_due` assertions (the two race tests and the disabled-notifications loop test), use `last_reminded_at` as described at the end of this step.

```python
def test_an_overdue_card_is_delivered_immediately(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due="2020-01-01T08:00:00+00:00")}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier)
    assert len(report.delivered) == 1
    assert len(notifier.sent) == 1
```

Add, using `timedelta`:

```python
def test_the_delivered_card_records_the_reminder_time(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    daemon.deliver_due(cards, states, moment, FakeNotifier())
    assert states["hello"].last_reminded_at == models.iso(moment)


def test_a_card_is_notified_again_after_ten_minutes(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    daemon.deliver_due(cards, states, moment, notifier)
    second = daemon.deliver_due(cards, states, moment + timedelta(minutes=10), notifier)
    assert len(notifier.sent) == 2
    assert len(second.delivered) == 1


def test_a_failing_notification_records_the_reminder_time(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    failing = FakeNotifier(notify.NotifyResult(False, 1, "Could not connect"))
    daemon.deliver_due(cards, states, moment, failing)
    assert states["hello"].last_reminded_at == models.iso(moment)


def test_a_failed_notification_is_not_retried_inside_the_slot(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    failing = FakeNotifier(notify.NotifyResult(False, 1, "Could not connect"))
    daemon.deliver_due(cards, states, moment, failing)
    daemon.deliver_due(cards, states, moment + timedelta(minutes=5), failing)
    assert len(failing.sent) == 1


def test_disabled_notifications_record_the_reminder_time(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier, notify_enabled=False)
    assert report.delivered == ()
    assert notifier.sent == []
    assert states["hello"].last_reminded_at == models.iso(moment)
```

Add the review-focus cadence test:

```python
def test_three_slots_three_notifications(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    for offset in (0, 10, 20):
        report = daemon.deliver_due(cards, states, moment + timedelta(minutes=offset), notifier)
        assert len(report.delivered) == 1
    assert len(notifier.sent) == 3
```

Update the two race tests to keep the grade assertions and change the final line to `assert saved.last_reminded_at is not None` (the reminder mark is applied to the freshly graded state; the grade's due, reps, interval and ease are what must survive). `test_a_notification_problem_and_the_recovery_are_logged` needs no rewrite: its first send adds a second due card (`world`), so the second iteration delivers `world` and logs the recovery. Keep it as it is.

Add a loop test next to `test_the_loop_sleeps_until_the_next_wakeup`:

```python
def test_the_loop_sleeps_until_the_next_reminder(home, monkeypatch):
    fixed = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(models, "now_utc", lambda: fixed)
    due = models.iso(fixed - timedelta(hours=1))
    reminded = models.iso(fixed - timedelta(minutes=4))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(
        paths.state_path(),
        {"hello": models.CardState(card_id="hello", due=due, last_reminded_at=reminded)},
    )
    timeouts = []

    def fake_select(read, write, error, timeout):
        timeouts.append(timeout)
        return ([], [], [])

    monkeypatch.setattr(daemon.select, "select", fake_select)
    assert daemon.run(max_iterations=1) == 0
    assert timeouts == [360.0]
```

Add a loop test for the disabled path next to the disabled-notifications test:

```python
def test_the_loop_ignores_reminder_slots_when_notifications_are_disabled(home, monkeypatch):
    fixed = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(models, "now_utc", lambda: fixed)
    due = models.iso(fixed - timedelta(hours=1))
    reminded = models.iso(fixed - timedelta(minutes=4))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(
        paths.state_path(),
        {"hello": models.CardState(card_id="hello", due=due, last_reminded_at=reminded)},
    )
    config.save_config(config.Config(notify_enabled=False))
    timeouts = []

    def fake_select(read, write, error, timeout):
        timeouts.append(timeout)
        return ([], [], [])

    monkeypatch.setattr(daemon.select, "select", fake_select)
    assert daemon.run(max_iterations=1) == 0
    assert timeouts == [3600.0]
```

In the disabled-notifications loop test, assert `last_reminded_at is not None` instead of `handled_due == due`. In `tests/test_cli.py`, change `test_a_daemon_mark_saved_during_a_grade_survives` to assert `states["later"].last_reminded_at == PAST`, and add:

```python
def test_grading_clears_the_reminder_clock(home, capsys):
    write_deck([make_card()])
    write_states(
        {
            "hello": models.CardState(
                card_id="hello", due=PAST, last_reminded_at="2026-10-21T08:00:00+00:00"
            )
        }
    )
    assert cli.main(["next", "good"]) == 0
    assert models.load_states(paths.state_path())["hello"].last_reminded_at is None
```

- [ ] **Step 10: Run the daemon and CLI tests to verify they fail**

Run: `python3 -m pytest tests/test_daemon.py tests/test_cli.py -q`
Expected: FAIL — `_mark_reminded` and the new report fields do not exist yet.

- [ ] **Step 11: Implement the daemon and diagnostics changes**

In `src/linguapulse/daemon.py`, replace the report, the marks and `deliver_due` with:

```python
@dataclass(frozen=True)
class DeliveryReport:
    """The outcome of one delivery round."""

    delivered: tuple[scheduler.Occurrence, ...]
    notified: bool
    message: str
    reminded: tuple[tuple[str, str], ...] = ()


def _mark_reminded(
    states: Mapping[str, models.CardState],
    occurrences: Sequence[scheduler.Occurrence],
    moment: datetime,
) -> tuple[tuple[str, str], ...]:
    """Record the reminder time on these cards and return their marks."""
    at = models.iso(moment)
    marks: list[tuple[str, str]] = []
    for occurrence in occurrences:
        state = occurrence.state
        if state is None:
            continue
        marks.append((occurrence.card.id, at))
        state.last_reminded_at = at
    return tuple(marks)


def _save_marks(marks: Sequence[tuple[str, str]]) -> dict[str, models.CardState]:
    """Apply the reminder marks to the current state file and save it.

    The states are read again right before the write, because a grade may
    have been recorded while the notification was being sent. Only the marks
    are applied, so the grade keeps its own due, interval and ease.
    """
    with store.state_lock():
        states = models.load_states(paths.state_path())
        for card_id, at in marks:
            state = states.setdefault(
                card_id, models.CardState(card_id=card_id, due=at, last_reminded_at=at)
            )
            state.last_reminded_at = at
        models.save_states(paths.state_path(), states)
    return states


def deliver_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
    notifier: Callable[[str, str], notify.NotifyResult] | None = None,
    notify_enabled: bool = True,
) -> DeliveryReport:
    """Deliver the reminder that is due and record when it was sent.

    The message of the report is only set when something went wrong, so that
    the caller can log it without writing a line for every empty round. The
    reminder marks are returned for the caller to persist, because the states
    it read may be out of date by the time the notification was sent. When
    notifications are disabled the due occurrences are marked without sending
    anything, and no reminder wakeup is scheduled.
    """
    send = notifier or notify.send
    pending = scheduler.pending_occurrences(cards, states, moment)
    group = scheduler.plan_reminder(pending)
    if not group:
        return DeliveryReport((), False, "")
    if not notify_enabled:
        marks = _mark_reminded(states, group, moment)
        return DeliveryReport((), False, "", marks)
    title, body = _notification_for(group)
    result = send(title, body)
    marks = _mark_reminded(states, group, moment)
    if result.ok:
        return DeliveryReport(group, True, "", marks)
    return DeliveryReport(
        group,
        False,
        result.message or "the notification failed",
        marks,
    )
```

In `run`, change `report.handled` to `report.reminded`, delete the `elif report.skipped:` branch, pass the setting into the wakeup, and change the disabled notice:

```python
                if report.reminded:
                    states = _save_marks(report.reminded)
                if not settings.notify_enabled:
                    if report.reminded and not disabled_notice:
                        print(
                            "notifications are disabled, advancing the reminder clock without sending",
                            file=sys.stderr,
                            flush=True,
                        )
                        disabled_notice = True
                else:
                    disabled_notice = False
                    if report.delivered:
                        print(f"delivered {len(report.delivered)} reminder(s)", flush=True)
                    if report.message and not report.notified:
                        if failures.should_log(report.message):
                            print(
                                f"notification problem: {report.message}",
                                file=sys.stderr,
                                flush=True,
                            )
                    elif report.notified and failures.recovered():
                        print(
                            "notifications are being delivered again",
                            file=sys.stderr,
                            flush=True,
                        )
                next_at = scheduler.next_wakeup(
                    cards, states, models.now_utc(), notify_enabled=settings.notify_enabled
                )
```

In `src/linguapulse/diagnostics.py`, load the settings inside the existing `try` and pass them to the wakeup:

```python
    try:
        cards = models.load_deck(paths.deck_path())
        states = models.load_states(paths.state_path())
        settings = config.load_config()
    except (OSError, TypeError, ValueError) as exc:
        return Check("schedule", False, f"the deck or state file cannot be read: {exc}")
    moment = models.now_utc()
    pending = scheduler.pending_occurrences(cards, states, moment)
    if pending:
        return Check("schedule", True, f"{_counted(len(pending), 'card')} due now")
    upcoming = scheduler.next_wakeup(
        cards, states, moment, notify_enabled=settings.notify_enabled
    )
```

- [ ] **Step 12: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS, with the previous count plus the new tests.

- [ ] **Step 13: Commit**

```bash
git add src/linguapulse/models.py src/linguapulse/srs.py src/linguapulse/scheduler.py \
  src/linguapulse/daemon.py src/linguapulse/diagnostics.py \
  tests/test_models.py tests/test_srs.py tests/test_scheduler.py tests/test_daemon.py \
  tests/test_cli.py tests/test_diagnostics.py docs/superpowers/specs/2026-10-23-repeat-reminders-design.md
git commit -m "feat: repeat a due reminder every 10 minutes until it is graded"
```

---

### Task 2: The spec and the README

**Files:**
- Modify: `plan.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-10-21-lingua-pulse.md` (the README copy in Task 15)

**Interfaces:**
- Consumes: the behaviour implemented in Task 1.
- Produces: documentation that matches the code.

- [ ] **Step 1: Rewrite the notification policy in `plan.md` §2**

Replace the paragraph that starts "Attempt each scheduled notification once." with:

> Deliver each scheduled reminder once per 10-minute slot. A card that is due and ungraded is reminded again every 10 minutes, without a limit, until it is graded. If delivery fails, log an actionable diagnostic, keep the scheduler running, and retry at the next 10-minute slot rather than in a tight loop. Rate-limit repeated identical failure messages and report when delivery recovers.

- [ ] **Step 2: Rewrite `plan.md` §9 and its acceptance criteria**

Replace §9 (from "### 9. Scheduling and Missed Reminders" through the end of the Wakeup Policy bullets) with:

```markdown
### 9. Scheduling and Repeated Reminders

- Use the system's local timezone and local wall-clock time for schedules, including across daylight-saving transitions.
- A card that is due and ungraded is reminded at its due time and then every 10 minutes, without a limit, until it is graded.
- A reminder that fell due while the service was stopped is delivered once, immediately after the service starts, and the 10-minute cadence resumes from there. Never send one reminder per missed slot.
- Persist the time of the last reminder per card so a restart neither repeats a reminder inside the same 10-minute slot nor loses the cadence.
- A card graded with `again` is not notifiable: its relearn step stays silent.

#### Wakeup Policy

- The scheduler sleeps until the exact next event: a card's due time or a card's next 10-minute reminder.
- Do not run a periodic polling loop. A background thread that wakes on a fixed interval to check for due cards is not permitted.
- Each due or reminder event produces at most one wakeup; the number of wakeups is bounded by the number of events, not by elapsed time.
- Recompute the sleep target after every delivery so that a newly scheduled card or reminder is picked up without an extra wakeup.
- When notifications are disabled, no reminder wakeups are scheduled.
```

Replace acceptance criterion "Resume/restart catch-up follows the missed-reminder policy in section 9 without replaying a backlog." with "Resume/restart catch-up follows the repeated-reminder policy in section 9 without replaying more than one reminder." Replace "The scheduler wakes no more than once per due card, with no periodic polling loop (see the wakeup policy in section 9)." with "The scheduler wakes once per due or reminder event, with no periodic polling loop (see the wakeup policy in section 9)."

- [ ] **Step 3: Rewrite the README**

Change the intro sentence "reminds you once, exactly when the word is due." to "reminds you when the word is due and keeps reminding you until you grade it."

Change the intro bullet "One notification per due moment, never a pile of leftovers." to "A due card reminds you every 10 minutes until you grade it."

In "How the scheduler works", change the first paragraph to "When it wakes up it delivers one notification, records the reminder time and computes the next wake up." Replace the 15-minute and backlog bullets with:

```markdown
* A due card that you do not grade reminds you again every 10 minutes, without
  a limit, until you grade it.
* After a restart, a missed reminder is delivered once and the 10-minute
  cadence resumes from there; missed slots are never replayed.
```

In "How the notifications behave", change "One notification per due moment, no retries." to "A due card notifies at its due time and then every 10 minutes until you grade it." Change the `--no-notify` bullet to "`linguapulse config --no-notify` silences the desktop notifications; cards still come due, and no reminder wakeups are scheduled until notifications are enabled again."

- [ ] **Step 4: Copy the README into the plan's Task 15 block**

In `docs/superpowers/plans/2026-10-21-lingua-pulse.md`, replace the content between the ```` ```markdown ```` fence after "Replace `README.md`:" and its closing fence with the new `README.md`, byte for byte. Leave every other line of the plan untouched.

- [ ] **Step 5: Verify the README and the plan block are byte-identical**

Run:

```bash
python3 - <<'EOF'
import pathlib
readme = pathlib.Path("README.md").read_text(encoding="utf-8")
plan = pathlib.Path("docs/superpowers/plans/2026-10-21-lingua-pulse.md").read_text(encoding="utf-8")
start_marker = "Replace `README.md`:\n\n```markdown\n"
start = plan.index(start_marker) + len(start_marker)
end = plan.index("\n```\n\n- [ ] **Step 2: Run the whole test suite**", start)
assert plan[start:end] == readme.rstrip("\n")
print("README and Task 15 block match")
EOF
```

Expected: `README and Task 15 block match`.

- [ ] **Step 6: Check for stale statements**

Run: `grep -n "15 minutes late\|never a pile\|one notification per due moment\|no retries\|marked handled" README.md plan.md`
Expected: no output.

- [ ] **Step 7: Run the full suite and commit**

Run: `python3 -m pytest`
Expected: PASS.

```bash
git add README.md plan.md docs/superpowers/plans/2026-10-21-lingua-pulse.md
git commit -m "docs: describe the repeated 10-minute reminders"
```

---

### Task 3: End-to-end verification

**Files:**
- No source changes.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: evidence that the cadence, restart behaviour and disabled path work outside the unit tests.

- [ ] **Step 1: Run the whole suite**

Run: `python3 -m pytest`
Expected: PASS.

- [ ] **Step 2: Exercise one overdue card in a scratch home**

```bash
export LINGUAPULSE_HOME=/tmp/opencode/lp-repeat
rm -rf "$LINGUAPULSE_HOME"
env PYTHONPATH=src python3 -m linguapulse add --term hello --lang zh --text 你好 --pinyin 'nǐ hǎo'
env PYTHONPATH=src python3 -m linguapulse config --target-lang zh
timeout 4 env PYTHONPATH=src python3 -m linguapulse daemon
env PYTHONPATH=src python3 -m linguapulse status
```

Expected: the daemon prints `delivered 1 reminder(s)`, one desktop notification appears, and `state.json` now has a `last_reminded_at` value. The card stays ungraded, so `status` still lists it as due.

- [ ] **Step 3: Confirm a fresh slot is silent and an expired slot notifies**

```bash
python3 - <<'EOF'
import datetime as dt
import json
import pathlib

path = pathlib.Path("/tmp/opencode/lp-repeat/data/state.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["cards"]["hello"]["last_reminded_at"] = (
    dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)
).isoformat()
path.write_text(json.dumps(data), encoding="utf-8")
EOF
timeout 3 env PYTHONPATH=src python3 -m linguapulse daemon
```

Expected: no `delivered` line, because the slot has 8 minutes left.

Then repeat the block with `timedelta(minutes=11)` and run the daemon again. Expected: `delivered 1 reminder(s)` and one notification.

- [ ] **Step 4: Confirm the disabled path**

```bash
env PYTHONPATH=src python3 -m linguapulse config --no-notify
python3 - <<'EOF'
import datetime as dt
import json
import pathlib

path = pathlib.Path("/tmp/opencode/lp-repeat/data/state.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["cards"]["hello"]["last_reminded_at"] = (
    dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=11)
).isoformat()
path.write_text(json.dumps(data), encoding="utf-8")
EOF
timeout 3 env PYTHONPATH=src python3 -m linguapulse daemon
```

Expected: `notifications are disabled, advancing the reminder clock without sending`, no desktop notification, and `last_reminded_at` updated to roughly now.

- [ ] **Step 5: Run three loop iterations with a patched clock**

```bash
env LINGUAPULSE_HOME=/tmp/opencode/lp-repeat-clock PYTHONPATH=src python3 - <<'EOF'
import datetime as dt
import shutil
from pathlib import Path

from linguapulse import config, daemon, models, notify, paths

home = Path("/tmp/opencode/lp-repeat-clock")
shutil.rmtree(home, ignore_errors=True)
paths.ensure_dirs()
fixed = dt.datetime(2026, 10, 21, 9, 0, tzinfo=dt.timezone.utc)
card = models.Card(
    id="hello",
    term="hello",
    source_lang="en",
    translations={"zh": "你好"},
    created_at=models.iso(fixed - dt.timedelta(days=1)),
)
models.save_deck(paths.deck_path(), {"hello": card})
models.save_states(
    paths.state_path(),
    {"hello": models.CardState(card_id="hello", due=models.iso(fixed - dt.timedelta(minutes=1)))},
)
config.save_config(config.Config(source_lang="en", target_lang="zh"))

clock = [fixed]
models.now_utc = lambda: clock[0]
sent = []


def fake_send(title, body):
    sent.append(title)
    return notify.NotifyResult(True, 0, "")


def advance(read, write, error, timeout):
    clock[0] += dt.timedelta(minutes=10)
    return ([], [], [])


daemon.notify.send = fake_send
daemon.select.select = advance
assert daemon.run(max_iterations=3, idle_timeout=0.0) == 0
assert len(sent) == 3, sent
print(f"three slots, {len(sent)} notifications")
EOF
```

Expected: `three slots, 3 notifications`.

- [ ] **Step 6: Report the results**

Record the observed notifications, the state file contents and the suite count. Do not commit anything in this task.

---

## Deployment (after the branch is merged)

```bash
pipx install --force .
systemctl --user restart linguapulse.service
linguapulse doctor
```

The deployed service then notifies every 10 minutes for the 7 currently overdue, ungraded cards until each is graded.
