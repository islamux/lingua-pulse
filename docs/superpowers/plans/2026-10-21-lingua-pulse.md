# LinguaPulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a terminal-first vocabulary trainer with per-card spaced repetition, optional desktop notifications through `notify-send`, and a background scheduler that runs as a `systemd --user` service on a minimal herbstluftwm Linux desktop.

**Architecture:** A single stdlib-only Python package (`linguapulse`) with a `src/` layout and an argparse CLI. Cards, scheduling state and review history are local JSON files under the XDG base directories. The scheduler is a separate process that holds an exclusive `flock` on a lock file, sleeps with `select()` until the exact due time of the next card, and delivers one notification per due occurrence through `notify-send`. The CLI and the scheduler coordinate through a PID file and `SIGHUP`, so a grade or a new card is picked up without polling.

**Tech Stack:** Python 3.11+ (standard library only at runtime), `argparse`, `dataclasses`, `zoneinfo`, `json`, `fcntl`, `select`, `pytest` for tests, `hatchling` as the build backend, `notify-send` and `systemd --user` for the system integration.

**Spec:** `plan.md` (repository root) — the plan argues from that spec, so the spec travels with it; executors read both.

**Status:** The code of every task was extracted from this document, assembled in a scratch directory and executed: 143 tests pass, the command line interface was exercised end to end, the generated unit file passes `systemd-analyze --user verify`, and the scheduler starts, refuses a second instance and stops on `SIGTERM`.

## Global Constraints

These apply to every task. They are copied from `plan.md` and are not up for reinterpretation.

- Python 3.11+ with the standard library only at runtime: no third-party import may appear anywhere under `src/linguapulse/` (`plan.md` §6).
- Storage is local JSON files under the XDG base directories (`plan.md` §6).
- The only system integration is `notify-send` plus a `systemd --user` service (`plan.md` §1, §4, §6).
- No system tray, graphical settings window, Electron frontend, web server, background database server, or dependency on a complete desktop environment (`plan.md` §6).
- `linguapulse show`, `linguapulse next`, `linguapulse history`, `linguapulse status` and `linguapulse validate` must work with no graphical interface (`plan.md` §5).
- Supported languages are `ar`, `en`, `es`, `fr`, `tr`, `zh`; Chinese cards carry pinyin with tone marks (`plan.md` §5).
- Terminal output must handle Arabic, Latin and Simplified Chinese correctly, and must not assume every terminal font covers them (`plan.md` §5).
- Schedules use the system local timezone and local wall-clock time, including across daylight-saving transitions (`plan.md` §9).
- The scheduler sleeps until the exact due time of the next card, never runs a periodic polling loop, produces at most one wakeup per due card, and recomputes its target after every delivery (`plan.md` §9).
- After a wake or a service restart only the latest overdue reminder is sent, and only when it is no more than 15 minutes late; missed reminders are never replayed (`plan.md` §9).
- The identity of the last delivered occurrence is persisted so a restart cannot send it twice (`plan.md` §9).
- Each scheduled notification is attempted once; a failure is logged with an actionable message, the scheduler keeps running, that reminder is not retried, identical failures are rate limited, and recovery is reported (`plan.md` §2).
- `notify-send` presence is checked at startup but no visible test notification is sent (`plan.md` §2).
- The existing herbstluftwm autostart file is never overwritten or replaced; a manual installation procedure and the way to undo it are documented (`plan.md` §3).
- The service is started with `systemctl --user start linguapulse.service`; no session-specific environment value is hardcoded (`plan.md` §3, §4).
- Duplicate schedulers are prevented when the user logs in or reloads the window manager configuration (`plan.md` §7).
- The Git repository is verified and inspected before work, each task runs on a fresh descriptive branch, pre-existing user changes are preserved, and commits, pushes and pull requests happen only when the user explicitly requests them (`plan.md` §10).

## Review Focus

The spec is a vision document: its silence about an input is not permission for that input to break the program. These are the five failure modes most likely to bite a real user, and each one is pinned by a test in the task that owns the code.

1. **Arabic text in a mixed line reorders the label.** A line such as `ar: مرحبا` must keep its label in place and its value in reading order, so right-to-left values are wrapped in directional isolates while left-to-right values are left untouched (`tests/test_text.py::test_isolate_wraps_only_right_to_left_text`).
2. **A deck edited by hand contains decomposed pinyin.** A Chinese card written with `xi` and a combining caron instead of `xiě` must be reported by `linguapulse validate` rather than silently mis-rendered (`tests/test_models.py::test_validate_reports_decomposed_text`).
3. **The scheduler restarts after a long downtime.** A backlog of reminders from the last three hours must not be replayed; at most the latest one is sent, and only within a 15 minute grace window (`tests/test_scheduler.py::test_stale_backlog_is_not_delivered`).
4. **The service and the window manager both start the scheduler.** The second instance must refuse to start and leave the first one running instead of double-scheduling every card (`tests/test_daemon.py::test_the_lock_excludes_a_second_scheduler`).
5. **The systemd unit starts without the session bus in its environment.** A notification must still reach the daemon on the bus, so the bus address falls back to `unix:path=$XDG_RUNTIME_DIR/bus` when `DBUS_SESSION_BUS_ADDRESS` is missing (`tests/test_notify.py::test_session_bus_address_falls_back_to_the_runtime_directory`).

---

### Task 0: Establish the Git Baseline

**Files:**
- Modify: none
- Test: none

**Interfaces:**
- Consumes: the current repository state (Git initialised, no commits, `plan.md` untracked, branch `docs/plan-sleep-until-due`).
- Produces: a baseline commit on `docs/plan-sleep-until-due` containing `plan.md` and `docs/superpowers/plans/2026-10-21-lingua-pulse.md`. Every later task branches from this commit.

- [ ] **Step 1: Inspect the repository state**

Run:

```bash
cd /media/islamux/Variety/Python_Projects/lingua-pulse
git status --porcelain=v1
git branch --show-current
git log --oneline -3
```

Expected: `?? plan.md`, `?? docs/`, branch `docs/plan-sleep-until-due`, and a "does not have any commits yet" error from `git log`.

- [ ] **Step 2: Ask the user for permission to commit**

`plan.md` §10 states that commits happen only when the user explicitly requests them. Ask: "May I create the baseline commit with `plan.md` and the implementation plan?" Do not commit without an explicit yes.

- [ ] **Step 3: Create the baseline commit**

```bash
git add plan.md docs/superpowers/plans/2026-10-21-lingua-pulse.md
git commit -m "docs: add the lingua-pulse specification and implementation plan"
```

Expected: one new commit on `docs/plan-sleep-until-due`.

- [ ] **Step 4: Record the branch naming rule**

Every following task starts with `git checkout -b <type>/<slug>` from the branch that holds the previous task's work. Suggested names: `feat/packaging-skeleton`, `feat/unicode-text-helpers`, `feat/xdg-paths-and-storage`, `feat/deck-models`, `feat/spaced-repetition`, `feat/user-config`, `feat/notification-delivery`, `feat/reminder-policy`, `feat/review-selection`, `feat/cli-review-commands`, `feat/cli-deck-commands`, `feat/scheduler-daemon`, `feat/diagnostics`, `feat/service-installation`, `docs/readme-and-verification`.

---

### Task 1: Package Skeleton and Version

**Files:**
- Create: `pyproject.toml`
- Create: `src/linguapulse/__init__.py`
- Create: `src/linguapulse/__main__.py`
- Create: `src/linguapulse/cli.py`
- Create: `tests/test_package.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `linguapulse.__version__: str` (`"0.1.0"`), `linguapulse.cli.main(argv: list[str] | None = None) -> int`, `linguapulse.cli.build_parser() -> argparse.ArgumentParser`. The console script `linguapulse` maps to `linguapulse.cli:main`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_package.py`:

```python
import tomllib
from pathlib import Path

import pytest

from linguapulse import __version__


def test_version_is_exported():
    assert __version__ == "0.1.0"


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_cli_version_flag(capsys):
    from linguapulse.cli import main

    assert main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_cli_help_returns_zero(capsys):
    from linguapulse.cli import main

    assert main(["--help"]) == 0
    capsys.readouterr()


def test_cli_unknown_flag_returns_two(capsys):
    from linguapulse.cli import main

    assert main(["--not-a-real-flag"]) == 2
    capsys.readouterr()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_package.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse'`.

- [ ] **Step 3: Write the minimal implementation**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[project]
name = "lingua-pulse"
version = "0.1.0"
description = "Terminal first vocabulary trainer with spaced repetition for minimal Linux desktops"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
linguapulse = "linguapulse.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/linguapulse"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q"
```

Create `src/linguapulse/__init__.py`:

```python
"""LinguaPulse: a terminal first vocabulary trainer with spaced repetition."""

__version__ = "0.1.0"

__all__ = ["__version__"]
```

Create `src/linguapulse/__main__.py`:

```python
"""Entry point for ``python -m linguapulse``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

Create `src/linguapulse/cli.py`:

```python
"""Command line interface.

The full command set is added by later tasks. This module owns the argument
parser and the dispatch table, so every later task only registers one more
command.
"""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top level argument parser."""
    parser = argparse.ArgumentParser(
        prog="linguapulse",
        description="Terminal first vocabulary trainer with spaced repetition.",
    )
    parser.add_argument("--version", action="version", version=f"linguapulse {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface and return the process exit code.

    The parser ends the process for `--help` and for a wrong usage, that
    exit code is returned instead, so that `main` always returns a number.
    """
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as request:
        return int(request.code or 0)
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_package.py -v`

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add pyproject.toml src/linguapulse tests/test_package.py
git commit -m "feat: add the package skeleton and version"
```

---

### Task 2: Unicode Text Helpers

**Files:**
- Create: `src/linguapulse/text.py`
- Create: `tests/test_text.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `text.normalize(text: str) -> str`, `text.char_width(ch: str) -> int`, `text.display_width(text: str) -> int`, `text.pad(text: str, width: int, align: str = "left") -> str`, `text.contains_rtl(text: str) -> bool`, `text.isolate(text: str) -> str`, `text.strip_isolates(text: str) -> str`, and the constants `text.LRI`, `text.RLI`, `text.FSI`, `text.PDI`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_text.py`:

```python
from linguapulse import text


def test_normalize_returns_nfc_form():
    decomposed = "xi\u030c"
    assert text.normalize(decomposed) == "x\u01d0"
    assert text.normalize(decomposed) != decomposed


def test_char_width_reports_the_columns_of_one_character():
    assert text.char_width("a") == 1
    assert text.char_width("你") == 2
    assert text.char_width("\u0301") == 0
    assert text.char_width(text.PDI) == 0


def test_display_width_counts_latin_and_arabic_as_one_column():
    assert text.display_width("hello") == 5
    assert text.display_width("مرحبا") == 5


def test_display_width_counts_chinese_as_two_columns():
    assert text.display_width("你好") == 4
    assert text.display_width("，") == 2


def test_display_width_ignores_combining_marks():
    assert text.display_width("é") == 1
    assert text.display_width("e\u0301") == 1


def test_display_width_ignores_directional_isolates():
    assert text.display_width(text.isolate("مرحبا")) == 5


def test_pad_uses_display_width_not_character_count():
    assert text.pad("你好", 6) == "你好  "
    assert text.pad("ab", 4) == "ab  "
    assert text.pad("ab", 4, align="right") == "  ab"


def test_pad_centers_the_text_in_the_gap():
    assert text.pad("ab", 6, align="center") == "  ab  "


def test_pad_keeps_text_that_is_wider_than_the_width():
    assert text.pad("你好", 2) == "你好"


def test_contains_rtl_detects_right_to_left_scripts():
    assert text.contains_rtl("مرحبا") is True
    assert text.contains_rtl("hello") is False
    assert text.contains_rtl("nǐ hǎo") is False


def test_isolate_wraps_only_right_to_left_text():
    assert text.isolate("hello") == "hello"
    assert text.isolate("مرحبا") == "⁧مرحبا⁩"


def test_strip_isolates_removes_every_marker():
    assert text.strip_isolates("⁦a⁧b⁨c⁩") == "abc"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_text.py -v`

Expected: FAIL with `ImportError: cannot import name 'text' from 'linguapulse'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/text.py`:

```python
"""Unicode helpers for rendering mixed direction text in a terminal."""

from __future__ import annotations

import unicodedata

LRI = "⁦"
RLI = "⁧"
FSI = "⁨"
PDI = "⁩"

_ZERO_WIDTH_CATEGORIES = frozenset({"Mn", "Me", "Cf"})


def normalize(text: str) -> str:
    """Return the text in Unicode Normalization Form C."""
    return unicodedata.normalize("NFC", text)


def char_width(ch: str) -> int:
    """Return the number of terminal columns a single character occupies."""
    if unicodedata.category(ch) in _ZERO_WIDTH_CATEGORIES:
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    """Return the number of terminal columns a string occupies."""
    return sum(char_width(ch) for ch in text)


def pad(text: str, width: int, align: str = "left") -> str:
    """Pad the text to the given number of terminal columns."""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def contains_rtl(text: str) -> bool:
    """Return True when the text holds characters with a right to left direction."""
    return any(unicodedata.bidirectional(ch) in ("R", "AL", "AN") for ch in text)


def isolate(text: str) -> str:
    """Wrap right to left text in directional isolates.

    Text without right to left characters is returned unchanged, so terminals
    without bidirectional support are not disturbed by the markers.
    """
    if not text or not contains_rtl(text):
        return text
    return RLI + text + PDI


def strip_isolates(text: str) -> str:
    """Remove every directional isolate marker from the text."""
    for marker in (LRI, RLI, FSI, PDI):
        text = text.replace(marker, "")
    return text
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_text.py -v`

Expected: PASS, 12 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/text.py tests/test_text.py
git commit -m "feat: add unicode helpers for mixed direction terminal output"
```


---

### Task 3: XDG Paths and Atomic Storage

**Files:**
- Create: `src/linguapulse/paths.py`
- Create: `src/linguapulse/store.py`
- Create: `tests/test_paths.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `paths.ENV_HOME = "LINGUAPULSE_HOME"`, `paths.data_dir() -> Path`, `paths.config_dir() -> Path`, `paths.state_dir() -> Path`, `paths.deck_path() -> Path`, `paths.state_path() -> Path`, `paths.history_path() -> Path`, `paths.config_path() -> Path`, `paths.lock_path() -> Path`, `paths.pid_path() -> Path`, `paths.ensure_dirs() -> None`, `store.read_json(path: Path, default: Any = None) -> Any`, `store.write_json(path: Path, payload: Any) -> None`, `store.append_jsonl(path: Path, payload: Any) -> None`, `store.read_jsonl(path: Path) -> list[Any]`, `store.state_lock(path: Path | None = None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_paths.py`:

```python
from linguapulse import paths


def test_home_override_keeps_everything_in_one_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    assert paths.data_dir() == tmp_path / "data"
    assert paths.config_dir() == tmp_path / "config"
    assert paths.state_dir() == tmp_path / "state"


def test_files_live_in_the_expected_directories(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    assert paths.deck_path() == tmp_path / "data" / "deck.json"
    assert paths.state_path() == tmp_path / "data" / "state.json"
    assert paths.history_path() == tmp_path / "data" / "history.jsonl"
    assert paths.config_path() == tmp_path / "config" / "config.json"
    assert paths.lock_path() == tmp_path / "state" / "daemon.lock"
    assert paths.pid_path() == tmp_path / "state" / "daemon.pid"


def test_xdg_variables_are_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "conf"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert paths.data_dir() == tmp_path / "share" / "linguapulse"
    assert paths.config_dir() == tmp_path / "conf" / "linguapulse"
    assert paths.state_dir() == tmp_path / "state" / "linguapulse"


def test_ensure_dirs_creates_all_directories(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    assert paths.data_dir().is_dir()
    assert paths.config_dir().is_dir()
    assert paths.state_dir().is_dir()
```

Create `tests/test_store.py`:

```python
import json

import pytest

from linguapulse import store


def test_read_json_returns_the_default_when_the_file_is_missing(tmp_path):
    assert store.read_json(tmp_path / "missing.json", {"a": 1}) == {"a": 1}


def test_read_json_raises_on_broken_json(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        store.read_json(broken, None)


def test_read_json_raises_a_plain_value_error_for_a_broken_document(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        store.read_json(broken, None)
    assert not isinstance(excinfo.value, json.JSONDecodeError)
    assert str(broken) in str(excinfo.value)


def test_write_json_keeps_unicode_unescaped(tmp_path):
    target = tmp_path / "deck.json"
    store.write_json(target, {"term": "مرحبا"})
    assert "مرحبا" in target.read_text(encoding="utf-8")


def test_write_json_replaces_the_file_atomically(tmp_path):
    target = tmp_path / "deck.json"
    store.write_json(target, {"version": 1})
    store.write_json(target, {"version": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}
    assert list(tmp_path.glob("*.tmp")) == []


def test_jsonl_round_trip_skips_broken_lines(tmp_path):
    target = tmp_path / "history.jsonl"
    store.append_jsonl(target, {"card_id": "a"})
    with target.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    store.append_jsonl(target, {"card_id": "b"})
    assert store.read_jsonl(target) == [{"card_id": "a"}, {"card_id": "b"}]


def test_read_jsonl_returns_an_empty_list_when_the_file_is_missing(tmp_path):
    assert store.read_jsonl(tmp_path / "missing.jsonl") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_paths.py tests/test_store.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.paths'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/paths.py`:

```python
"""Filesystem locations that follow the XDG base directory specification."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "linguapulse"
ENV_HOME = "LINGUAPULSE_HOME"


def _override_root() -> Path | None:
    raw = os.environ.get(ENV_HOME)
    return Path(raw).expanduser() if raw else None


def _xdg(variable: str, fallback: str) -> Path:
    raw = os.environ.get(variable)
    base = Path(raw).expanduser() if raw else Path.home() / fallback
    return base / APP_NAME


def data_dir() -> Path:
    """Return the directory that holds the deck, the state and the history."""
    root = _override_root()
    if root is not None:
        return root / "data"
    return _xdg("XDG_DATA_HOME", ".local/share")


def config_dir() -> Path:
    """Return the directory that holds the configuration file."""
    root = _override_root()
    if root is not None:
        return root / "config"
    return _xdg("XDG_CONFIG_HOME", ".config")


def state_dir() -> Path:
    """Return the directory that holds the lock and the process id file."""
    root = _override_root()
    if root is not None:
        return root / "state"
    return _xdg("XDG_STATE_HOME", ".local/state")


def deck_path() -> Path:
    """Return the path of the deck file."""
    return data_dir() / "deck.json"


def state_path() -> Path:
    """Return the path of the scheduling state file."""
    return data_dir() / "state.json"


def history_path() -> Path:
    """Return the path of the review history file."""
    return data_dir() / "history.jsonl"


def config_path() -> Path:
    """Return the path of the configuration file."""
    return config_dir() / "config.json"


def lock_path() -> Path:
    """Return the path of the scheduler lock file."""
    return state_dir() / "daemon.lock"


def pid_path() -> Path:
    """Return the path of the scheduler process id file."""
    return state_dir() / "daemon.pid"


def ensure_dirs() -> None:
    """Create the data, config and state directories when they are missing."""
    for directory in (data_dir(), config_dir(), state_dir()):
        directory.mkdir(parents=True, exist_ok=True)
```

Create `src/linguapulse/store.py`:

```python
"""Atomic JSON and JSON Lines persistence helpers."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from . import paths


def read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON document, returning the default when the file is absent."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    """Write a JSON document, replacing the target file in a single step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def state_lock(path: Path | None = None) -> Iterator[None]:
    """Serialize the writers of the state file with an exclusive file lock.

    Every writer re-reads the state file under this lock and applies only its
    own change, so a scheduler mark and a grade recorded at the same moment
    never overwrite each other. The lock is never held while a notification
    is sent.
    """
    target = path or paths.state_dir() / "state.lock"
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = open(target, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def append_jsonl(path: Path, payload: Any) -> None:
    """Append one JSON object as a line to a JSON Lines file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_jsonl(path: Path) -> list[Any]:
    """Read a JSON Lines file, skipping blank and malformed lines."""
    if not path.exists():
        return []
    entries: list[Any] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_paths.py tests/test_store.py -v`

Expected: PASS, 11 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/paths.py src/linguapulse/store.py tests/test_paths.py tests/test_store.py
git commit -m "feat: add xdg paths and atomic json storage"
```

---

### Task 4: Deck Models, Validation and the Local Time Zone

**Files:**
- Create: `src/linguapulse/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: `store.read_json(path, default)` and `store.write_json(path, payload)` from Task 3.
- Produces: `models.SUPPORTED_LANGUAGES: tuple[str, ...]`, `models.PINYIN_TONE_MARKS: frozenset[str]`, `models.now_utc() -> datetime`, `models.iso(moment: datetime) -> str`, `models.parse_iso(value: str) -> datetime`, `models.safe_parse_iso(value: str) -> datetime | None`, `models.local_zone() -> tzinfo`, `models.add_wall_clock(base: datetime, days: float, zone: tzinfo) -> datetime`, `models.Card`, `models.CardState`, `models.load_deck(path: Path) -> dict[str, Card]`, `models.save_deck(path: Path, deck: Mapping[str, Card]) -> None`, `models.load_states(path: Path) -> dict[str, CardState]`, `models.save_states(path: Path, states: Mapping[str, CardState]) -> None`, `models.validate_deck_raw(raw: Mapping[str, Any]) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from linguapulse import models


def make_card(card_id="hello", **overrides):
    data = {
        "id": card_id,
        "term": "hello",
        "source_lang": "en",
        "translations": {"ar": "مرحبا", "zh": "你好"},
        "pinyin": "nǐ hǎo",
    }
    data.update(overrides)
    return models.Card.from_dict(data)


def test_card_round_trip_keeps_every_field():
    card = make_card(notes="greeting", tags=["greetings"], created_at="2026-10-21T09:00:00+00:00")
    assert models.Card.from_dict(card.to_dict()) == card


def test_load_deck_returns_an_empty_deck_when_the_file_is_missing(tmp_path):
    assert models.load_deck(tmp_path / "deck.json") == {}


def test_save_and_load_deck_round_trip(tmp_path):
    deck = {"hello": make_card()}
    target = tmp_path / "deck.json"
    models.save_deck(target, deck)
    assert models.load_deck(target) == deck


def test_load_deck_rejects_a_file_without_cards(tmp_path):
    target = tmp_path / "deck.json"
    target.write_text('{"version": 1}', encoding="utf-8")
    try:
        models.load_deck(target)
    except ValueError as exc:
        assert "not a valid deck file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_deck_rejects_a_null_card(tmp_path):
    target = tmp_path / "deck.json"
    target.write_text('{"cards": {"hello": null}}', encoding="utf-8")
    try:
        models.load_deck(target)
    except ValueError as exc:
        assert "not a valid deck file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_deck_rejects_a_card_that_is_not_an_object(tmp_path):
    target = tmp_path / "deck.json"
    target.write_text('{"cards": {"hello": "a card"}}', encoding="utf-8")
    try:
        models.load_deck(target)
    except ValueError as exc:
        assert "not a valid deck file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_card_state_round_trip():
    state = models.CardState(
        card_id="hello",
        due="2026-10-22T09:00:00+00:00",
        handled_due="2026-10-21T09:00:00+00:00",
    )
    assert models.CardState.from_dict(state.to_dict()) == state


def test_card_state_due_dt_parses_the_timestamp():
    state = models.CardState(card_id="hello", due="2026-10-22T09:00:00+00:00")
    assert state.due_dt() == datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


def test_load_states_returns_an_empty_mapping_when_the_file_is_missing(tmp_path):
    assert models.load_states(tmp_path / "state.json") == {}


def test_save_and_load_states_round_trip(tmp_path):
    states = {
        "hello": models.CardState(
            card_id="hello",
            due="2026-10-22T09:00:00+00:00",
            handled_due="2026-10-21T09:00:00+00:00",
        )
    }
    target = tmp_path / "state.json"
    models.save_states(target, states)
    assert models.load_states(target) == states


def test_load_states_rejects_a_file_without_cards(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"version": 1}', encoding="utf-8")
    try:
        models.load_states(target)
    except ValueError as exc:
        assert "is not a valid state file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_states_rejects_a_null_card(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"cards": {"hello": null}}', encoding="utf-8")
    try:
        models.load_states(target)
    except ValueError as exc:
        assert "is not a valid state file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_states_rejects_a_card_that_is_not_an_object(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"cards": {"hello": "a card"}}', encoding="utf-8")
    try:
        models.load_states(target)
    except ValueError as exc:
        assert "is not a valid state file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_validate_accepts_a_correct_card():
    raw = {"cards": {"hello": make_card().to_dict()}}
    assert models.validate_deck_raw(raw) == []


def test_validate_reports_a_missing_pinyin_for_chinese():
    card = make_card().to_dict()
    card["pinyin"] = ""
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("no 'pinyin'" in problem for problem in problems)


def test_validate_reports_pinyin_without_tone_marks():
    card = make_card().to_dict()
    card["pinyin"] = "ni hao"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("no tone marks" in problem for problem in problems)


def test_validate_reports_pinyin_with_a_bare_umlaut_as_having_no_tone_marks():
    card = make_card().to_dict()
    card["pinyin"] = "lü"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("no tone marks" in problem for problem in problems)


def test_validate_reports_decomposed_text():
    card = make_card().to_dict()
    card["term"] = "xi\u030c"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("Normalization Form C" in problem for problem in problems)


def test_validate_reports_an_unsupported_language():
    card = make_card().to_dict()
    card["translations"]["de"] = "hallo"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("unsupported language" in problem for problem in problems)


def test_validate_reports_an_empty_term():
    card = make_card().to_dict()
    card["term"] = "  "
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("'term' is empty" in problem for problem in problems)


def test_local_zone_prefers_the_tz_variable(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    assert str(models.local_zone()) == "Europe/Berlin"


def test_add_wall_clock_keeps_the_local_time_of_day_across_a_dst_change():
    zone = ZoneInfo("Europe/Berlin")
    before = datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)
    after = models.add_wall_clock(before, 1, zone)
    assert after.astimezone(zone).strftime("%Y-%m-%d %H:%M") == "2026-03-29 10:00"
    assert after == datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)


def test_safe_parse_iso_returns_none_for_broken_input():
    assert models.safe_parse_iso("not a timestamp") is None
    assert models.safe_parse_iso("2026-10-22T09:00:00+00:00") == datetime(
        2026, 10, 22, 9, 0, tzinfo=timezone.utc
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.models'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/models.py`:

```python
"""Deck, card and scheduling state models."""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import store

SUPPORTED_LANGUAGES = ("ar", "en", "es", "fr", "tr", "zh")
PINYIN_TONE_MARKS = frozenset("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")


def now_utc() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    """Format a datetime as an ISO 8601 UTC timestamp."""
    return moment.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp into an aware UTC datetime."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def safe_parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 timestamp, returning None when it cannot be parsed."""
    try:
        return parse_iso(value)
    except (TypeError, ValueError):
        return None


def _zone_from_name(name: str) -> tzinfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def local_zone() -> tzinfo:
    """Return the system timezone, resolved without hardcoding a location.

    The lookup order is the TZ environment variable, then /etc/timezone, then
    the /etc/localtime symlink target. UTC is the final fallback.
    """
    zone = _zone_from_name(os.environ.get("TZ", ""))
    if zone is not None:
        return zone
    try:
        name = Path("/etc/timezone").read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
    zone = _zone_from_name(name)
    if zone is not None:
        return zone
    try:
        target = os.readlink("/etc/localtime")
    except OSError:
        target = ""
    marker = "zoneinfo/"
    if marker in target:
        zone = _zone_from_name(target.split(marker, 1)[1])
        if zone is not None:
            return zone
    return timezone.utc


def add_wall_clock(base: datetime, days: float, zone: tzinfo) -> datetime:
    """Add a wall-clock duration, keeping the same local time of day.

    A daylight-saving transition does not move the scheduled local time, so a
    one day interval stays one day apart on the wall clock.
    """
    local = base.astimezone(zone)
    naive = local.replace(tzinfo=None) + timedelta(days=days)
    return naive.replace(tzinfo=zone, fold=0).astimezone(timezone.utc)


@dataclass
class Card:
    """One vocabulary entry."""

    id: str
    term: str
    source_lang: str = "en"
    translations: dict[str, str] = field(default_factory=dict)
    pinyin: str | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "term": self.term,
            "source_lang": self.source_lang,
            "translations": dict(self.translations),
            "pinyin": self.pinyin,
            "notes": self.notes,
            "tags": list(self.tags),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Card":
        translations = raw.get("translations") or {}
        pinyin = raw.get("pinyin")
        return cls(
            id=str(raw.get("id", "")),
            term=str(raw.get("term", "")),
            source_lang=str(raw.get("source_lang", "en")),
            translations={str(key): str(value) for key, value in dict(translations).items()},
            pinyin=str(pinyin) if pinyin else None,
            notes=str(raw.get("notes", "")),
            tags=[str(tag) for tag in (raw.get("tags") or [])],
            created_at=str(raw.get("created_at", "")),
        )

    def has_translation(self, lang: str) -> bool:
        """Return True when the card carries a translation for the language."""
        return lang in self.translations


@dataclass
class CardState:
    """The scheduling state of one card."""

    card_id: str
    due: str
    interval_days: float = 0.0
    ease: float = 2.5
    reps: int = 0
    lapses: int = 0
    last_graded_at: str | None = None
    handled_due: str | None = None
    notifiable: bool = True

    def due_dt(self) -> datetime:
        """Return the due time as an aware UTC datetime."""
        return parse_iso(self.due)

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "due": self.due,
            "interval_days": self.interval_days,
            "ease": self.ease,
            "reps": self.reps,
            "lapses": self.lapses,
            "last_graded_at": self.last_graded_at,
            "handled_due": self.handled_due,
            "notifiable": self.notifiable,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CardState":
        return cls(
            card_id=str(raw.get("card_id", "")),
            due=str(raw.get("due", "")),
            interval_days=float(raw.get("interval_days", 0.0)),
            ease=float(raw.get("ease", 2.5)),
            reps=int(raw.get("reps", 0)),
            lapses=int(raw.get("lapses", 0)),
            last_graded_at=raw.get("last_graded_at"),
            handled_due=raw.get("handled_due"),
            notifiable=bool(raw.get("notifiable", True)),
        )


def load_deck(path: Path) -> dict[str, Card]:
    """Load the deck from disk, returning an empty deck when the file is absent."""
    raw = store.read_json(path, None)
    if raw is None:
        return {}
    cards = raw.get("cards") if isinstance(raw, Mapping) else None
    if not isinstance(cards, Mapping):
        raise ValueError(f"{path} is not a valid deck file")
    deck: dict[str, Card] = {}
    for card_id, card_raw in cards.items():
        if not isinstance(card_raw, Mapping):
            raise ValueError(
                f"{path} is not a valid deck file: card {card_id!r} is not an object"
            )
        data = dict(card_raw)
        data.setdefault("id", card_id)
        card = Card.from_dict(data)
        deck[card.id] = card
    return deck


def save_deck(path: Path, deck: Mapping[str, Card]) -> None:
    """Write the deck to disk atomically."""
    store.write_json(
        path,
        {"version": 1, "cards": {card_id: card.to_dict() for card_id, card in deck.items()}},
    )


def load_states(path: Path) -> dict[str, CardState]:
    """Load the scheduling state, returning an empty mapping when it is absent."""
    raw = store.read_json(path, None)
    if raw is None:
        return {}
    cards = raw.get("cards") if isinstance(raw, Mapping) else None
    if not isinstance(cards, Mapping):
        raise ValueError(f"{path} is not a valid state file")
    states: dict[str, CardState] = {}
    for card_id, state_raw in cards.items():
        if not isinstance(state_raw, Mapping):
            raise ValueError(
                f"{path} is not a valid state file: card {card_id!r} is not an object"
            )
        data = dict(state_raw)
        data.setdefault("card_id", card_id)
        states[str(card_id)] = CardState.from_dict(data)
    return states


def save_states(path: Path, states: Mapping[str, CardState]) -> None:
    """Write the scheduling state to disk atomically."""
    store.write_json(
        path,
        {"version": 1, "cards": {card_id: state.to_dict() for card_id, state in states.items()}},
    )


def _check_normalized(problems: list[str], label: str, field_name: str, value: str) -> None:
    if value != unicodedata.normalize("NFC", value):
        problems.append(f"{label}: {field_name} is not in Unicode Normalization Form C")


def validate_deck_raw(raw: Mapping[str, Any]) -> list[str]:
    """Validate a raw deck document and return the list of problems found."""
    problems: list[str] = []
    if not isinstance(raw, Mapping):
        return ["deck file is not a JSON object"]
    cards = raw.get("cards")
    if not isinstance(cards, Mapping):
        return ["deck file has no 'cards' object"]
    seen: set[str] = set()
    for card_id, card_raw in cards.items():
        label = str(card_id)
        if not isinstance(card_raw, Mapping):
            problems.append(f"{label}: card entry is not an object")
            continue
        stored_id = str(card_raw.get("id", label))
        if stored_id != label:
            problems.append(f"{label}: 'id' field is {stored_id!r} but the key is {label!r}")
        if stored_id in seen:
            problems.append(f"{label}: duplicate card id")
        seen.add(stored_id)
        source_lang = str(card_raw.get("source_lang", "en"))
        if source_lang not in SUPPORTED_LANGUAGES:
            problems.append(f"{label}: unsupported source language {source_lang!r}")
        term = str(card_raw.get("term", ""))
        if not term.strip():
            problems.append(f"{label}: 'term' is empty")
        _check_normalized(problems, label, "term", term)
        translations = card_raw.get("translations")
        if not isinstance(translations, Mapping) or not translations:
            problems.append(f"{label}: 'translations' is missing or empty")
            translations = {}
        for lang, value in sorted(translations.items(), key=lambda item: str(item[0])):
            language = str(lang)
            if language not in SUPPORTED_LANGUAGES:
                problems.append(f"{label}: unsupported language {language!r}")
            translation = str(value)
            if not translation.strip():
                problems.append(f"{label}: translation for {language!r} is empty")
            _check_normalized(problems, label, f"translations.{language}", translation)
        pinyin = card_raw.get("pinyin")
        if pinyin:
            pinyin_text = str(pinyin)
            _check_normalized(problems, label, "pinyin", pinyin_text)
            if "zh" not in translations:
                problems.append(f"{label}: 'pinyin' is set but there is no 'zh' translation")
            elif not any(mark in PINYIN_TONE_MARKS for mark in pinyin_text):
                problems.append(f"{label}: pinyin {pinyin_text!r} contains no tone marks")
        if "zh" in translations and not pinyin:
            problems.append(f"{label}: 'zh' translation has no 'pinyin'")
    return problems
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_models.py -v`

Expected: PASS, 23 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/models.py tests/test_models.py
git commit -m "feat: add deck models, validation and local timezone handling"
```


---

### Task 5: Spaced Repetition Grading

**Files:**
- Create: `src/linguapulse/srs.py`
- Create: `tests/test_srs.py`

**Interfaces:**
- Consumes: `models.CardState`, `models.now_utc`, `models.iso`, `models.add_wall_clock`, `models.local_zone` from Task 4.
- Produces: `srs.GRADES: tuple[str, ...]`, `srs.DEFAULT_EASE: float`, `srs.MIN_EASE: float`, `srs.MAX_EASE: float`, `srs.MAX_INTERVAL_DAYS: float`, `srs.RELEARN_MINUTES: int`, `srs.GRACE_MINUTES: int`, `srs.new_state(card_id: str, moment: datetime | None = None) -> models.CardState`, `srs.apply_grade(state: models.CardState, grade: str, moment: datetime | None = None, zone: tzinfo | None = None) -> models.CardState`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_srs.py`:

```python
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from linguapulse import models, srs

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
ZONE = ZoneInfo("UTC")


def test_new_state_is_due_immediately():
    state = srs.new_state("hello", NOW)
    assert state.due == models.iso(NOW)
    assert state.reps == 0
    assert state.ease == srs.DEFAULT_EASE
    assert state.notifiable is True


def test_good_on_a_new_card_schedules_one_day():
    state = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    assert state.interval_days == 1.0
    assert state.due_dt() == NOW + timedelta(days=1)
    assert state.reps == 1


def test_good_on_the_second_review_schedules_six_days():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    second = srs.apply_grade(first, "good", NOW, ZONE)
    assert second.interval_days == 6.0


def test_hard_grows_the_interval_slowly_and_lowers_the_ease():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    second = srs.apply_grade(first, "hard", NOW, ZONE)
    assert second.interval_days == pytest.approx(1.2)
    assert second.ease == pytest.approx(srs.DEFAULT_EASE - 0.15)


def test_easy_multiplies_the_interval_and_raises_the_ease():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    second = srs.apply_grade(first, "easy", NOW, ZONE)
    assert second.interval_days == pytest.approx(8.0)
    assert second.ease == pytest.approx(srs.DEFAULT_EASE + 0.15)


def test_again_schedules_a_ten_minute_relearn_and_resets_the_reps():
    state = srs.apply_grade(srs.new_state("hello", NOW), "again", NOW, ZONE)
    assert state.due_dt() == NOW + timedelta(minutes=srs.RELEARN_MINUTES)
    assert state.reps == 0
    assert state.lapses == 1
    assert state.notifiable is False


def test_ease_never_falls_below_the_minimum():
    state = srs.new_state("hello", NOW)
    for _ in range(10):
        state = srs.apply_grade(state, "again", NOW, ZONE)
    assert state.ease == srs.MIN_EASE


def test_ease_never_rises_above_the_maximum():
    state = srs.new_state("hello", NOW)
    for _ in range(20):
        state = srs.apply_grade(state, "easy", NOW, ZONE)
    assert state.ease == srs.MAX_EASE


def test_the_interval_is_capped():
    state = srs.new_state("hello", NOW)
    for _ in range(30):
        state = srs.apply_grade(state, "easy", NOW, ZONE)
    assert state.interval_days == srs.MAX_INTERVAL_DAYS


def test_grading_clears_the_handled_occurrence():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    first.handled_due = first.due
    second = srs.apply_grade(first, "good", NOW, ZONE)
    assert second.handled_due is None


def test_an_unknown_grade_is_rejected():
    with pytest.raises(ValueError):
        srs.apply_grade(srs.new_state("hello", NOW), "perfect", NOW, ZONE)


def test_a_day_interval_keeps_the_local_time_of_day_across_a_dst_change():
    zone = ZoneInfo("Europe/Berlin")
    before = datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)
    state = srs.apply_grade(srs.new_state("hello", before), "good", before, zone)
    assert state.due_dt().astimezone(zone).strftime("%Y-%m-%d %H:%M") == "2026-03-29 10:00"


def test_apply_grade_does_not_mutate_the_input_state():
    state = srs.new_state("hello", NOW)
    before = (
        state.due,
        state.interval_days,
        state.ease,
        state.reps,
        state.lapses,
        state.handled_due,
        state.notifiable,
    )
    _ = srs.apply_grade(state, "good", NOW, ZONE)
    after = (
        state.due,
        state.interval_days,
        state.ease,
        state.reps,
        state.lapses,
        state.handled_due,
        state.notifiable,
    )
    assert after == before
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_srs.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.srs'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/srs.py`:

```python
"""Spaced repetition grading and interval computation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

from . import models

GRADES = ("again", "hard", "good", "easy")
DEFAULT_EASE = 2.5
MIN_EASE = 1.3
MAX_EASE = 2.8
MAX_INTERVAL_DAYS = 365.0
RELEARN_MINUTES = 10
GRACE_MINUTES = 15


def new_state(card_id: str, moment: datetime | None = None) -> models.CardState:
    """Create the initial scheduling state of a card."""
    moment = moment or models.now_utc()
    return models.CardState(
        card_id=card_id,
        due=models.iso(moment),
        interval_days=0.0,
        ease=DEFAULT_EASE,
        reps=0,
        lapses=0,
        notifiable=True,
    )


def apply_grade(
    state: models.CardState,
    grade: str,
    moment: datetime | None = None,
    zone: tzinfo | None = None,
) -> models.CardState:
    """Return the state of a card after it was graded."""
    if grade not in GRADES:
        raise ValueError(f"unknown grade: {grade!r}")
    moment = moment or models.now_utc()
    zone = zone or models.local_zone()

    ease = state.ease
    reps = state.reps
    lapses = state.lapses
    interval = state.interval_days
    notifiable = True

    if grade == "again":
        interval = RELEARN_MINUTES / 1440.0
        ease = max(MIN_EASE, ease - 0.20)
        reps = 0
        lapses += 1
        notifiable = False
    elif grade == "hard":
        interval = max(1.0, interval * 1.2) if reps > 0 else 1.0
        ease = max(MIN_EASE, ease - 0.15)
        reps += 1
    elif grade == "good":
        if reps == 0:
            interval = 1.0
        elif reps == 1:
            interval = 6.0
        else:
            interval = interval * ease
        reps += 1
    else:
        if reps == 0:
            interval = 3.0
        elif reps == 1:
            interval = 8.0
        else:
            interval = interval * ease * 1.3
        ease = min(MAX_EASE, ease + 0.15)
        reps += 1

    interval = min(interval, MAX_INTERVAL_DAYS)
    if grade == "again":
        due = (moment + timedelta(minutes=RELEARN_MINUTES)).astimezone(timezone.utc)
    else:
        due = models.add_wall_clock(moment, interval, zone)

    return models.CardState(
        card_id=state.card_id,
        due=models.iso(due),
        interval_days=interval,
        ease=ease,
        reps=reps,
        lapses=lapses,
        last_graded_at=models.iso(moment),
        handled_due=None,
        notifiable=notifiable,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_srs.py -v`

Expected: PASS, 13 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/srs.py tests/test_srs.py
git commit -m "feat: add spaced repetition grading"
```

---

### Task 6: User Configuration

**Files:**
- Create: `src/linguapulse/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `paths.config_path()`, `store.read_json`, `store.write_json` from Task 3.
- Produces: `config.Config` (fields `source_lang: str`, `target_lang: str`, `notify_enabled: bool`) with `to_dict()` and `from_dict(raw)`, `config.load_config() -> Config`, `config.save_config(settings: Config) -> None`, `config.DEFAULT_SOURCE_LANG = "en"`, `config.DEFAULT_TARGET_LANG = "ar"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from linguapulse import config, models, paths


def test_defaults_are_used_when_no_file_exists(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG
    assert settings.target_lang == config.DEFAULT_TARGET_LANG
    assert settings.notify_enabled is True


def test_saving_and_loading_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    config.save_config(config.Config(source_lang="ar", target_lang="zh", notify_enabled=False))
    settings = config.load_config()
    assert settings.source_lang == "ar"
    assert settings.target_lang == "zh"
    assert settings.notify_enabled is False


def test_a_broken_file_falls_back_to_the_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    paths.config_path().write_text('{"source_lang": 5}', encoding="utf-8")
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG


def test_a_file_that_is_not_valid_json_falls_back_to_the_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    paths.config_path().write_text("{not json", encoding="utf-8")
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG
    assert settings.target_lang == config.DEFAULT_TARGET_LANG
    assert settings.notify_enabled is True


def test_an_unsupported_language_falls_back_to_the_default(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    paths.config_path().write_text(
        '{"source_lang": "de", "target_lang": "fr"}', encoding="utf-8"
    )
    assert "de" not in models.SUPPORTED_LANGUAGES
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG
    assert settings.target_lang == "fr"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.config'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/config.py`:

```python
"""User preferences stored in the configuration directory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import paths, store

DEFAULT_SOURCE_LANG = "en"
DEFAULT_TARGET_LANG = "ar"


@dataclass
class Config:
    """The preferences that steer the CLI and the scheduler."""

    source_lang: str = DEFAULT_SOURCE_LANG
    target_lang: str = DEFAULT_TARGET_LANG
    notify_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "notify_enabled": self.notify_enabled,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "Config":
        """Build a configuration from a raw document, ignoring broken values."""
        settings = cls()
        if not isinstance(raw, Mapping):
            return settings
        source = raw.get("source_lang")
        target = raw.get("target_lang")
        if isinstance(source, str) and source.strip():
            settings.source_lang = source.strip()
        if isinstance(target, str) and target.strip():
            settings.target_lang = target.strip()
        if "notify_enabled" in raw:
            settings.notify_enabled = bool(raw["notify_enabled"])
        return settings


def load_config() -> Config:
    """Load the configuration, falling back to the defaults."""
    return Config.from_dict(store.read_json(paths.config_path(), {}))


def save_config(settings: Config) -> None:
    """Write the configuration to disk atomically."""
    store.write_json(paths.config_path(), settings.to_dict())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_config.py -v`

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/config.py tests/test_config.py
git commit -m "feat: add user configuration"
```

---

### Task 7: Notification Delivery

**Files:**
- Create: `src/linguapulse/notify.py`
- Create: `tests/test_notify.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `notify.NotifyResult(ok: bool, code: int, message: str)`, `notify.notify_send_path(env=None) -> str | None`, `notify.session_bus_address(env=None) -> str | None`, `notify.child_environment(env=None) -> dict[str, str]`, `notify.notification_daemon(env=None) -> str | None`, `notify.send(title: str, body: str, *, env=None, urgency: str = "normal", timeout: float = 10.0) -> NotifyResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify.py`:

```python
from linguapulse import notify


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


BUS_ENV = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus", "PATH": "/usr/bin:/bin"}


def test_session_bus_address_prefers_the_dbus_variable():
    assert notify.session_bus_address(BUS_ENV) == "unix:path=/run/user/1000/bus"


def test_session_bus_address_falls_back_to_the_runtime_directory():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000", "PATH": "/usr/bin:/bin"}
    assert notify.session_bus_address(env) == "unix:path=/run/user/1000/bus"


def test_session_bus_address_is_none_without_any_hint():
    assert notify.session_bus_address({"PATH": "/usr/bin:/bin"}) is None


def test_child_environment_always_carries_a_bus_address():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000", "PATH": "/usr/bin:/bin"}
    assert notify.child_environment(env)["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"


def test_notify_send_path_is_none_when_it_is_not_installed():
    assert notify.notify_send_path({"PATH": "/nonexistent"}) is None


def test_notify_send_path_is_none_without_a_path_in_the_environment():
    assert notify.notify_send_path({"XDG_RUNTIME_DIR": "/run/user/1000"}) is None


def test_the_notification_daemon_is_not_looked_up_without_a_path(monkeypatch):
    listing = (
        "NAME                           PID PROCESS  USER  CONNECTION  UNIT\n"
        "org.freedesktop.Notifications  3576 dunst    user  :1.20       app-org.freedesktop.Notifications.service\n"
    )
    monkeypatch.setattr(
        notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0, listing)
    )
    env = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
    assert notify.notification_daemon(env) is None


def test_send_without_notify_send_reports_an_actionable_error():
    result = notify.send("title", "body", env={"PATH": "/nonexistent", "XDG_RUNTIME_DIR": "/run/user/1000"})
    assert result.ok is False
    assert result.code == 127
    assert "notify-send" in result.message


def test_send_without_a_session_bus_explains_the_problem(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    result = notify.send("title", "body", env={"PATH": "/usr/bin:/bin"})
    assert result.ok is False
    assert "session bus" in result.message


def test_send_reports_the_error_of_a_failing_notify_send(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompleted(1, "", "Could not connect: No such file or directory"),
    )
    result = notify.send("title", "body", env=BUS_ENV)
    assert result.ok is False
    assert result.code == 1
    assert "Could not connect" in result.message


def test_send_reports_success(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0))
    result = notify.send("title", "body", env=BUS_ENV)
    assert result.ok is True
    assert result.code == 0


def test_send_reports_a_timeout_as_a_failure(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")

    def fake_run(args, **kwargs):
        raise notify.subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    result = notify.send("title", "body", env=BUS_ENV)
    assert result.ok is False
    assert result.code == 124
    assert "timed out" in result.message


def test_the_bus_address_is_passed_to_the_child_process(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["env"] = kwargs.get("env")
        return FakeCompleted(0)

    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    notify.send("title", "body", env={"XDG_RUNTIME_DIR": "/run/user/1000", "PATH": "/usr/bin:/bin"})
    assert captured["env"]["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"


def test_the_arguments_carry_the_title_and_the_body(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return FakeCompleted(0)

    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    notify.send("learned word", "the body of the notification", env=BUS_ENV, urgency="critical")
    args = captured["args"]
    assert args[0] == "/usr/bin/notify-send"
    assert "--urgency=critical" in args
    separator = args.index("--")
    assert args[separator + 1] == "learned word"
    assert args[separator + 2] == "the body of the notification"
    assert args[separator + 3 :] == []
    notify.send("title", "body", env=BUS_ENV)
    assert "--urgency=normal" in captured["args"]


def test_the_notification_daemon_is_read_from_the_bus(monkeypatch):
    listing = (
        "NAME                           PID PROCESS  USER  CONNECTION  UNIT\n"
        "org.freedesktop.Notifications  3576 dunst    user  :1.20       app-org.freedesktop.Notifications.service\n"
    )
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/busctl")
    monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0, listing))
    assert notify.notification_daemon(BUS_ENV) == "dunst"


def test_no_notification_daemon_is_reported_as_none(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/busctl")
    monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0, "NAME PID PROCESS\n"))
    assert notify.notification_daemon(BUS_ENV) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_notify.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.notify'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/notify.py`:

```python
"""Desktop notification delivery through notify-send."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping

NOTIFY_SEND = "notify-send"
BUSCTL = "busctl"
NOTIFICATIONS_BUS_NAME = "org.freedesktop.Notifications"
DBUS_SESSION_BUS_ADDRESS = "DBUS_SESSION_BUS_ADDRESS"


@dataclass(frozen=True)
class NotifyResult:
    """The outcome of one delivery attempt."""

    ok: bool
    code: int
    message: str


def _environment(env: Mapping[str, str] | None) -> dict[str, str]:
    return dict(os.environ if env is None else env)


def notify_send_path(env: Mapping[str, str] | None = None) -> str | None:
    """Return the absolute path of notify-send, or None when it is missing."""
    environment = _environment(env)
    return shutil.which(NOTIFY_SEND, path=environment.get("PATH") or "")


def session_bus_address(env: Mapping[str, str] | None = None) -> str | None:
    """Return the session bus address, or None when no bus can be reached."""
    environment = _environment(env)
    address = environment.get(DBUS_SESSION_BUS_ADDRESS)
    if address:
        return address
    runtime = environment.get("XDG_RUNTIME_DIR")
    if runtime:
        return f"unix:path={runtime}/bus"
    return None


def child_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a child process environment that carries a usable bus address."""
    environment = _environment(env)
    address = session_bus_address(environment)
    if address:
        environment[DBUS_SESSION_BUS_ADDRESS] = address
    return environment


def notification_daemon(env: Mapping[str, str] | None = None) -> str | None:
    """Return the name of the running notification daemon, or None."""
    environment = _environment(env)
    if session_bus_address(environment) is None:
        return None
    busctl = shutil.which(BUSCTL, path=environment.get("PATH") or "")
    if not busctl:
        return None
    try:
        completed = subprocess.run(
            [busctl, "--user", "--no-pager", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            env=child_environment(environment),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        columns = line.split()
        if columns and columns[0] == NOTIFICATIONS_BUS_NAME:
            return columns[2] if len(columns) > 2 else "unknown"
    return None


def send(
    title: str,
    body: str,
    *,
    env: Mapping[str, str] | None = None,
    urgency: str = "normal",
    timeout: float = 10.0,
) -> NotifyResult:
    """Deliver one notification. The caller decides whether to try again."""
    environment = _environment(env)
    binary = notify_send_path(environment)
    if binary is None:
        return NotifyResult(
            False,
            127,
            "notify-send is not installed; install the notify-send or libnotify-bin package",
        )
    if not session_bus_address(environment):
        return NotifyResult(
            False,
            1,
            "no session bus address; set DBUS_SESSION_BUS_ADDRESS or XDG_RUNTIME_DIR",
        )
    try:
        completed = subprocess.run(
            [binary, "--app-name=linguapulse", f"--urgency={urgency}", "--", title, body],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_environment(environment),
        )
    except subprocess.TimeoutExpired:
        return NotifyResult(False, 124, "notify-send timed out")
    except OSError as exc:
        return NotifyResult(False, 1, f"could not run notify-send: {exc}")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return NotifyResult(
            False,
            completed.returncode,
            detail or f"notify-send exited with status {completed.returncode}",
        )
    return NotifyResult(True, 0, "")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_notify.py -v`

Expected: PASS, 16 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/notify.py tests/test_notify.py
git commit -m "feat: add notification delivery with actionable diagnostics"
```


---

### Task 8: Reminder Policy

**Files:**
- Create: `src/linguapulse/scheduler.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `models.Card`, `models.CardState`, `models.safe_parse_iso` from Task 4, `srs.GRACE_MINUTES` from Task 5.
- Produces: `scheduler.Occurrence(card, due, state)` with the property `due_iso`, `scheduler.Reminder(due, group, skipped)` with the property `handled`, `scheduler.occurrence_due(card, state, moment) -> datetime`, `scheduler.pending_occurrences(cards, states, moment) -> list[Occurrence]`, `scheduler.next_wakeup(cards, states, moment) -> datetime | None`, `scheduler.plan_reminder(pending, moment) -> Reminder | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scheduler.py`:

```python
from datetime import datetime, timezone

from linguapulse import models, scheduler

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def make_card(card_id="hello", created_at="2026-10-20T09:00:00+00:00"):
    return models.Card(
        id=card_id,
        term=card_id,
        source_lang="en",
        translations={"ar": card_id},
        created_at=created_at,
    )


def state_for(card_id, due, **overrides):
    data = {"card_id": card_id, "due": due}
    data.update(overrides)
    return models.CardState.from_dict(data)


def test_pending_occurrences_holds_the_cards_that_are_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    assert [occurrence.card.id for occurrence in pending] == ["hello"]


def test_pending_occurrences_skips_cards_that_are_not_due_yet():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_pending_occurrences_skips_an_occurrence_that_was_already_handled():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello",
            "2026-10-21T08:00:00+00:00",
            handled_due="2026-10-21T08:00:00+00:00",
        )
    }
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_pending_occurrences_reminds_a_card_that_got_a_new_due_time():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello",
            "2026-10-21T08:00:00+00:00",
            handled_due="2026-10-20T08:00:00+00:00",
        )
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    assert [occurrence.card.id for occurrence in pending] == ["hello"]


def test_pending_occurrences_skips_relearn_cards():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:55:00+00:00", notifiable=False)}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_card_without_a_state_has_no_scheduled_review():
    cards = {"hello": make_card()}
    assert scheduler.pending_occurrences(cards, {}, NOW) == []
    assert scheduler.next_wakeup(cards, {}, NOW) is None


def test_a_card_without_a_state_does_not_suppress_a_card_that_is_due():
    cards = {
        "fresh": make_card("fresh", created_at="2026-10-21T08:58:00+00:00"),
        "due": make_card("due"),
    }
    states = {"due": state_for("due", "2026-10-21T08:55:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert [occurrence.card.id for occurrence in reminder.group] == ["due"]
    assert reminder.skipped == ()


def test_next_wakeup_returns_the_soonest_future_occurrence():
    cards = {"hello": make_card(), "world": make_card()}
    states = {
        "hello": state_for("hello", "2026-10-22T09:00:00+00:00"),
        "world": state_for("world", "2026-10-21T12:00:00+00:00"),
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_next_wakeup_is_none_without_a_future_occurrence():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-20T09:00:00+00:00")}
    assert scheduler.next_wakeup(cards, states, NOW) is None


def test_a_relearn_card_does_not_produce_a_wakeup():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T12:00:00+00:00", notifiable=False)}
    assert scheduler.next_wakeup(cards, states, NOW) is None


def test_an_already_handled_occurrence_does_not_produce_a_wakeup():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello",
            "2026-10-21T12:00:00+00:00",
            handled_due="2026-10-21T12:00:00+00:00",
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW) is None


def test_the_latest_overdue_reminder_within_the_grace_window_is_selected():
    cards = {"old": make_card("old"), "late": make_card("late")}
    states = {
        "old": state_for("old", "2026-10-21T06:00:00+00:00"),
        "late": state_for("late", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert [occurrence.card.id for occurrence in reminder.group] == ["late"]
    assert [occurrence.card.id for occurrence in reminder.skipped] == ["old"]
    assert reminder.due == datetime(2026, 10, 21, 8, 55, tzinfo=timezone.utc)


def test_a_reminder_that_is_exactly_at_the_grace_limit_is_delivered():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:45:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert [occurrence.card.id for occurrence in reminder.group] == ["hello"]
    assert reminder.skipped == ()


def test_older_reminders_are_never_replayed():
    cards = {"old": make_card("old"), "late": make_card("late")}
    states = {
        "old": state_for("old", "2026-10-21T06:00:00+00:00"),
        "late": state_for("late", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert len(reminder.handled) == 2


def test_stale_backlog_is_not_delivered():
    cards = {"old": make_card("old")}
    states = {"old": state_for("old", "2026-10-21T06:00:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert reminder.group == ()
    assert [occurrence.card.id for occurrence in reminder.skipped] == ["old"]


def test_cards_that_are_due_at_the_same_moment_form_one_group():
    cards = {"a": make_card("a"), "b": make_card("b")}
    states = {
        "a": state_for("a", "2026-10-21T08:55:00+00:00"),
        "b": state_for("b", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert sorted(occurrence.card.id for occurrence in reminder.group) == ["a", "b"]
    assert reminder.skipped == ()


def test_an_empty_backlog_plans_nothing():
    assert scheduler.plan_reminder([], NOW) is None


def test_a_broken_due_falls_back_to_the_creation_time():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "not a timestamp")}
    due = scheduler.occurrence_due(cards["hello"], states["hello"], NOW)
    assert due == datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def test_the_due_iso_of_an_occurrence_round_trips():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    assert models.safe_parse_iso(pending[0].due_iso) == pending[0].due
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_scheduler.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.scheduler'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/scheduler.py`:

```python
"""The policy that decides which due occurrences become reminders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from . import models
from .srs import GRACE_MINUTES


@dataclass(frozen=True)
class Occurrence:
    """One scheduled review of one card."""

    card: models.Card
    due: datetime
    state: models.CardState | None

    @property
    def due_iso(self) -> str:
        """Return the due time as an ISO 8601 timestamp."""
        return self.due.isoformat()


@dataclass(frozen=True)
class Reminder:
    """The outcome of planning a reminder for one wake up."""

    due: datetime
    group: tuple[Occurrence, ...]
    skipped: tuple[Occurrence, ...]

    @property
    def handled(self) -> tuple[Occurrence, ...]:
        """Return every occurrence that was acted on, delivered or skipped."""
        return self.group + self.skipped


def occurrence_due(
    card: models.Card,
    state: models.CardState | None,
    moment: datetime,
) -> datetime:
    """Return the time at which a card becomes due.

    A broken timestamp in the state file must not stop the scheduler, so the
    creation time of the card is used as the fallback.
    """
    if state is not None:
        due = models.safe_parse_iso(state.due)
        if due is not None:
            return due
    if card.created_at:
        parsed = models.safe_parse_iso(card.created_at)
        if parsed is not None:
            return parsed
    return moment


def _scheduled_review(
    card: models.Card,
    state: models.CardState | None,
    moment: datetime,
) -> Occurrence | None:
    """Return the scheduled review of a card, or None when it has none.

    A card without a state has no scheduled review: it is never due, it never
    wakes the scheduler up and it is never reminded. The relearn step of an
    "again" grade is not notifiable, so it is not reminded either. An
    occurrence that was already acted on is not a review any more.
    """
    if state is None or not state.notifiable:
        return None
    due = occurrence_due(card, state, moment)
    if state.handled_due:
        handled = models.safe_parse_iso(state.handled_due)
        if handled is not None and handled == due:
            return None
    return Occurrence(card=card, due=due, state=state)


def pending_occurrences(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[Occurrence]:
    """Return the occurrences that are due and that were not acted on yet."""
    pending: list[Occurrence] = []
    for card_id in sorted(cards):
        occurrence = _scheduled_review(cards[card_id], states.get(card_id), moment)
        if occurrence is None or occurrence.due > moment:
            continue
        pending.append(occurrence)
    return pending


def next_wakeup(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> datetime | None:
    """Return the exact time of the next occurrence worth waking up for."""
    candidates: list[datetime] = []
    for card_id in sorted(cards):
        occurrence = _scheduled_review(cards[card_id], states.get(card_id), moment)
        if occurrence is None or occurrence.due <= moment:
            continue
        candidates.append(occurrence.due)
    return min(candidates) if candidates else None


def plan_reminder(pending: Iterable[Occurrence], moment: datetime) -> Reminder | None:
    """Pick the single reminder to deliver and mark the older ones as skipped."""
    ordered = sorted(pending, key=lambda occurrence: occurrence.due)
    if not ordered:
        return None
    latest = ordered[-1].due
    group = tuple(occurrence for occurrence in ordered if occurrence.due == latest)
    older = tuple(occurrence for occurrence in ordered if occurrence.due != latest)
    if (moment - latest).total_seconds() > GRACE_MINUTES * 60:
        return Reminder(due=latest, group=(), skipped=tuple(ordered))
    return Reminder(due=latest, group=group, skipped=older)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_scheduler.py -v`

Expected: PASS, 19 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/scheduler.py tests/test_scheduler.py
git commit -m "feat: add the reminder policy with a grace window"
```

---

### Task 9: Card Selection and Rendering

**Files:**
- Create: `src/linguapulse/review.py`
- Create: `tests/test_review.py`

**Interfaces:**
- Consumes: `scheduler.occurrence_due` from Task 8, `models.Card` and `models.CardState` from Task 4, `text.isolate` from Task 2.
- Produces: `review.due_cards(cards, states, moment) -> list[models.Card]`, `review.current_card(cards, states, moment) -> models.Card | None`, `review.next_due(cards, states, moment) -> tuple[models.Card, datetime] | None`, `review.render_card(card, *, target_lang=None, reveal=False, index=None, total=None) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_review.py`:

```python
from datetime import datetime, timezone

from linguapulse import models, review

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def make_card(card_id="hello", created_at="2026-10-20T09:00:00+00:00"):
    return models.Card(
        id=card_id,
        term="hello",
        source_lang="en",
        translations={"ar": "مرحبا", "zh": "你好"},
        pinyin="nǐ hǎo",
        notes="a greeting",
        tags=["greetings"],
        created_at=created_at,
    )


def state_for(card_id, due, **overrides):
    data = {"card_id": card_id, "due": due}
    data.update(overrides)
    return models.CardState(**data)


def test_due_cards_orders_the_most_overdue_card_first():
    cards = {"later": make_card("later"), "earlier": make_card("earlier")}
    states = {
        "later": state_for("later", "2026-10-21T08:50:00+00:00"),
        "earlier": state_for("earlier", "2026-10-21T08:00:00+00:00"),
    }
    assert [card.id for card in review.due_cards(cards, states, NOW)] == ["earlier", "later"]


def test_due_cards_ignores_cards_that_are_not_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert review.due_cards(cards, states, NOW) == []


def test_due_cards_holds_a_card_without_a_state():
    cards = {"hello": make_card(created_at="2026-10-21T08:00:00+00:00")}
    assert [card.id for card in review.due_cards(cards, {}, NOW)] == ["hello"]


def test_due_cards_holds_a_relearn_card():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:55:00+00:00", notifiable=False)}
    assert [card.id for card in review.due_cards(cards, states, NOW)] == ["hello"]


def test_a_card_created_in_the_future_is_not_due():
    cards = {"hello": make_card(created_at="2026-10-21T10:00:00+00:00")}
    assert review.due_cards(cards, {}, NOW) == []
    card, when = review.next_due(cards, {}, NOW)
    assert card.id == "hello"
    assert when == datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


def test_current_card_returns_the_most_overdue_card():
    cards = {"later": make_card("later"), "earlier": make_card("earlier")}
    states = {
        "later": state_for("later", "2026-10-21T08:50:00+00:00"),
        "earlier": state_for("earlier", "2026-10-21T08:00:00+00:00"),
    }
    assert review.current_card(cards, states, NOW).id == "earlier"


def test_current_card_returns_none_when_nothing_is_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert review.current_card(cards, states, NOW) is None


def test_next_due_is_none_when_nothing_is_scheduled():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    assert review.next_due(cards, states, NOW) is None


def test_next_due_reports_the_soonest_future_card():
    cards = {"hello": make_card(), "world": make_card("world")}
    states = {
        "hello": state_for("hello", "2026-10-21T12:00:00+00:00"),
        "world": state_for("world", "2026-10-21T10:00:00+00:00"),
    }
    card, when = review.next_due(cards, states, NOW)
    assert card.id == "world"
    assert when == datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


def test_render_card_hides_the_translations_by_default():
    output = review.render_card(make_card())
    assert "hello" in output
    assert "مرحبا" not in output
    assert "a greeting" not in output


def test_render_card_reveals_the_translations():
    output = review.render_card(make_card(), reveal=True)
    assert "مرحبا" in output
    assert "你好" in output
    assert "a greeting" in output


def test_render_card_isolates_right_to_left_translations():
    output = review.render_card(make_card(), reveal=True)
    assert "ar: ⁧مرحبا⁩" in output


def test_render_card_shows_the_pinyin():
    assert "nǐ hǎo" in review.render_card(make_card())


def test_render_card_puts_the_requested_language_first():
    output = review.render_card(make_card(), reveal=True, target_lang="zh")
    assert output.index("zh:") < output.index("ar:")


def test_render_card_falls_back_to_the_sorted_languages():
    output = review.render_card(make_card(), reveal=True, target_lang="fr")
    assert output.index("ar:") < output.index("zh:")


def test_render_card_isolates_a_right_to_left_id():
    output = review.render_card(make_card(card_id="مرحبا"))
    assert output.splitlines()[0] == "⁧مرحبا⁩  [greetings]"


def test_render_card_isolates_right_to_left_tags():
    card = make_card()
    card.tags = ["تحية"]
    output = review.render_card(card)
    assert output.splitlines()[0] == "hello  [⁧تحية⁩]"


def test_render_card_shows_the_position_and_the_id():
    output = review.render_card(make_card(), index=2, total=7)
    assert output.splitlines()[0] == "2 of 7  (hello)  [greetings]"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_review.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'linguapulse.review'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/linguapulse/review.py`:

```python
"""Card selection and terminal rendering."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from . import models, scheduler, text


def _due_entries(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[tuple[datetime, str, models.Card]]:
    """Return the due time, the id and the card of every card, the earliest due first.

    The card id breaks the tie, so two cards that are due at the same moment always
    keep the same order.
    """
    entries = [
        (scheduler.occurrence_due(card, states.get(card_id), moment), card_id, card)
        for card_id, card in cards.items()
    ]
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return entries


def due_cards(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[models.Card]:
    """Return the cards that are due, the most overdue one first."""
    return [
        card for due, _, card in _due_entries(cards, states, moment) if due <= moment
    ]


def current_card(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> models.Card | None:
    """Return the card to review next, or None when nothing is due."""
    for due, _, card in _due_entries(cards, states, moment):
        if due <= moment:
            return card
    return None


def next_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> tuple[models.Card, datetime] | None:
    """Return the soonest card that is not due yet."""
    for due, _, card in _due_entries(cards, states, moment):
        if due > moment:
            return card, due
    return None


def render_card(
    card: models.Card,
    *,
    target_lang: str | None = None,
    reveal: bool = False,
    index: int | None = None,
    total: int | None = None,
) -> str:
    """Render a card for the terminal."""
    lines: list[str] = []
    identifier = text.isolate(card.id)
    heading = identifier
    if index is not None and total is not None:
        heading = f"{index} of {total}  ({identifier})"
    if card.tags:
        tags = ", ".join(text.isolate(tag) for tag in card.tags)
        heading = f"{heading}  [{tags}]"
    lines.append(heading)
    lines.append("")
    lines.append(f"{card.source_lang}: {text.isolate(card.term)}")
    if card.pinyin:
        lines.append(f"pinyin: {text.isolate(card.pinyin)}")
    if reveal:
        lines.append("")
        languages = sorted(card.translations)
        if target_lang and target_lang in card.translations:
            languages = [target_lang] + [lang for lang in languages if lang != target_lang]
        for language in languages:
            lines.append(f"{language}: {text.isolate(card.translations[language])}")
        if card.notes:
            lines.append(f"notes: {text.isolate(card.notes)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_review.py -v`

Expected: PASS, 18 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/review.py tests/test_review.py
git commit -m "feat: add card selection and terminal rendering"
```


---

### Task 10: Review Commands of the CLI

**Files:**
- Modify: `src/linguapulse/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `config.load_config` from Task 6, `models` from Task 4, `paths` from Task 3, `review` from Task 9, `srs` from Task 5, `store` from Task 3.
- Produces: `cli.main(argv) -> int`, `cli.build_parser()`, `cli.format_local(moment) -> str`, `cli.local_stamp(value) -> str`, `cli.plural(count, singular, plural_form=None) -> str`, `cli.load_session()`, `cli.resolve_language(language, fallback)`, `cli.report_nothing_due(cards, states, moment)`, `cli.command_show(args)`, `cli.command_next(args)`, `cli.command_history(args)`, `cli.command_status(args)`, `cli.command_validate(args)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from datetime import datetime

from conftest import (
    make_card,
    write_broken_deck,
    write_deck,
    write_malformed_deck,
    write_malformed_states,
    write_states,
)
from linguapulse import cli, config, daemon, models, paths, srs, store

PAST = "2020-01-01T09:00:00+00:00"
FUTURE = "2099-01-01T09:00:00+00:00"


def test_format_local_reads_a_naive_timestamp_as_utc(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    assert cli.format_local(datetime(2026, 10, 22, 9, 0)) == "2026-10-22 17:00 CST"


def test_show_prints_the_due_card_without_the_answer(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "مرحبا" not in out


def test_show_reveals_the_translations_on_request(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show", "--reveal"]) == 0
    assert "مرحبا" in capsys.readouterr().out


def test_show_reports_when_nothing_is_due(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=FUTURE)})
    assert cli.main(["show"]) == 0
    assert "Nothing is due" in capsys.readouterr().out


def test_show_uses_the_requested_language_without_storing_it(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show", "--reveal", "--lang", "zh"]) == 0
    out = capsys.readouterr().out
    assert out.index("zh:") < out.index("ar:")
    assert config.load_config().target_lang == "ar"


def test_show_shows_the_requested_number_of_cards(home, capsys):
    write_deck([make_card("hello"), make_card("world")])
    write_states(
        {
            "hello": models.CardState(card_id="hello", due=PAST),
            "world": models.CardState(card_id="world", due=PAST),
        }
    )
    assert cli.main(["show", "--count", "2"]) == 0
    out = capsys.readouterr().out
    assert "1 of 2" in out
    assert "2 of 2" in out


def test_show_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["show"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "is not valid JSON" in captured.err


def test_show_reports_a_broken_state_file(home, capsys):
    write_deck([make_card()])
    paths.state_path().write_text("{", encoding="utf-8")
    assert cli.main(["show"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "is not valid JSON" in captured.err


def test_show_reports_a_malformed_state_file(home, capsys):
    write_deck([make_card()])
    write_malformed_states()
    assert cli.main(["show"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "NoneType" in captured.err


def test_show_rejects_an_unknown_language(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show", "--lang", "xx"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "error: unknown language 'xx', the supported languages are "
        "ar, en, es, fr, tr, zh" in captured.err
    )


def test_next_grades_the_due_card_and_records_the_review(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["next", "good"]) == 0
    assert "Graded 'good'" in capsys.readouterr().out
    states = models.load_states(paths.state_path())
    assert states["hello"].reps == 1
    entries = store.read_jsonl(paths.history_path())
    assert entries[-1]["card_id"] == "hello"
    assert entries[-1]["grade"] == "good"


def test_a_daemon_mark_saved_during_a_grade_survives(home, capsys, monkeypatch):
    write_deck([make_card("hello"), make_card("later")])
    write_states(
        {
            "hello": models.CardState(card_id="hello", due=PAST),
            "later": models.CardState(card_id="later", due=PAST),
        }
    )
    original = srs.apply_grade

    def grade_after_the_daemon_marks(state, grade, moment=None, zone=None):
        daemon._save_marks([("later", PAST)])
        return original(state, grade, moment, zone)

    monkeypatch.setattr(cli.srs, "apply_grade", grade_after_the_daemon_marks)
    assert cli.main(["next", "good"]) == 0
    states = models.load_states(paths.state_path())
    assert states["later"].handled_due == PAST
    assert states["hello"].reps == 1


def test_next_reports_when_nothing_is_due(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=FUTURE)})
    assert cli.main(["next", "good"]) == 0
    assert "Nothing is due" in capsys.readouterr().out


def test_next_hides_the_translations_on_request(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["next", "good", "--hide"]) == 0
    out = capsys.readouterr().out
    assert "مرحبا" not in out
    assert "Graded 'good'" in out


def test_next_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["next", "good"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "is not valid JSON" in captured.err


def test_next_reports_a_malformed_state_file(home, capsys):
    write_deck([make_card()])
    write_malformed_states()
    assert cli.main(["next", "good"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "NoneType" in captured.err


def test_next_rejects_an_unknown_language(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["next", "good", "--lang", "xx"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "error: unknown language 'xx', the supported languages are "
        "ar, en, es, fr, tr, zh" in captured.err
    )


def test_history_lists_the_recorded_reviews(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    assert cli.main(["history"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "good" in out


def test_history_filters_by_card(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    assert cli.main(["history", "--card", "other"]) == 0
    assert "No reviews" in capsys.readouterr().out


def test_history_limits_the_number_of_entries(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    assert cli.main(["history", "--limit", "1"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len([line for line in lines if "good" in line]) == 1


def test_history_prints_the_local_time(home, capsys, monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    store.append_jsonl(
        paths.history_path(),
        {
            "ts": "2020-01-01T09:00:00+00:00",
            "card_id": "hello",
            "grade": "good",
            "due": "2020-01-02T09:00:00+00:00",
        },
    )
    assert cli.main(["history"]) == 0
    out = capsys.readouterr().out
    assert "2020-01-01 17:00 CST" in out
    assert "2020-01-02 17:00 CST" in out
    assert "2020-01-01T09:00:00+00:00" not in out


def test_history_keeps_a_broken_timestamp(home, capsys):
    paths.history_path().write_text(
        '{"ts": "not a time", "card_id": "hello", "grade": "good"}\n', encoding="utf-8"
    )
    assert cli.main(["history"]) == 0
    assert "not a time" in capsys.readouterr().out


def test_status_reports_the_deck_size(home, capsys):
    write_deck([make_card()])
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "1 card" in out
    assert "Time zone" in out


def test_status_reports_the_due_cards_the_next_card_and_the_languages(home, capsys):
    write_deck([make_card("hello"), make_card("later")])
    write_states(
        {
            "hello": models.CardState(card_id="hello", due=PAST),
            "later": models.CardState(card_id="later", due=FUTURE),
        }
    )
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "2 cards" in out
    assert "1 card" in out
    assert "later" in out
    assert "Languages: source en, target ar" in out


def test_status_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["status"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "is not valid JSON" in captured.err


def test_status_reports_a_malformed_state_file(home, capsys):
    write_deck([make_card()])
    write_malformed_states()
    assert cli.main(["status"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "NoneType" in captured.err


def test_validate_accepts_a_clean_deck(home, capsys):
    write_deck([make_card()])
    assert cli.main(["validate"]) == 0
    assert "no problems found" in capsys.readouterr().out


def test_validate_reports_a_broken_card(home, capsys):
    card = make_card()
    card.term = ""
    write_deck([card])
    assert cli.main(["validate"]) == 1
    out = capsys.readouterr().out
    assert "problem" in out
    assert "term" in out


def test_validate_reports_a_missing_deck(home, capsys):
    assert cli.main(["validate"]) == 1
    assert "No deck file" in capsys.readouterr().out


def test_validate_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["validate"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "problem:" in captured.out
    assert "is not valid JSON" in captured.out


def test_validate_reports_a_malformed_deck_file(home, capsys):
    write_malformed_deck()
    assert cli.main(["validate"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "problem: 'int' object is not iterable" in captured.out
    assert "1 problem found." in captured.out
```

Add the shared fixtures and helpers to `tests/conftest.py`:

```python
import pytest

from linguapulse import models, paths


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Point every XDG directory of lingua-pulse at a temporary directory."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    return tmp_path


def make_card(card_id="hello"):
    """Return a small card used by the CLI tests."""
    return models.Card(
        id=card_id,
        term="hello",
        source_lang="en",
        translations={"ar": "مرحبا", "zh": "你好"},
        pinyin="nǐ hǎo",
        created_at="2020-01-01T09:00:00+00:00",
    )


def write_deck(cards):
    """Write cards to the deck file."""
    models.save_deck(paths.deck_path(), {card.id: card for card in cards})


def write_broken_deck():
    """Write a deck file that is not valid JSON."""
    paths.deck_path().write_text('{"version": 1, "cards": {', encoding="utf-8")


def write_malformed_deck():
    """Write a deck file that is valid JSON but holds a wrongly typed field."""
    paths.deck_path().write_text(
        '{"version": 1, "cards": {"hello": {"id": "hello", "term": "hello", '
        '"source_lang": "en", "translations": {"ar": "مرحبا"}, "tags": 5}}}\n',
        encoding="utf-8",
    )


def write_malformed_states():
    """Write a state file that is valid JSON but holds a wrongly typed field."""
    paths.state_path().write_text(
        '{"version": 1, "cards": {"hello": {"card_id": "hello", '
        '"due": "2020-01-01T09:00:00+00:00", "reps": null}}}\n',
        encoding="utf-8",
    )


def write_states(states):
    """Write card states to the state file."""
    models.save_states(paths.state_path(), states)
```

Add this import at the top of `tests/test_cli.py`, so that the file uses the shared helpers:

```python
from conftest import (
    make_card,
    write_broken_deck,
    write_deck,
    write_malformed_deck,
    write_malformed_states,
    write_states,
)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -v`

Expected: FAIL because `cli.main` does not know the `show` command yet.

- [ ] **Step 3: Write the implementation**

Replace `src/linguapulse/cli.py` with:

```python
"""Command line interface.

Every command is registered in one place, so each later task only adds one
entry to the parser and one entry to the dispatch table.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import __version__, config, models, paths, review, srs, store


def format_local(moment: datetime) -> str:
    """Format a timestamp in the local time zone.

    A timestamp without a time zone is read as UTC, the way `models.parse_iso`
    reads it, so that the two agree on what a naive timestamp means.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(models.local_zone()).strftime("%Y-%m-%d %H:%M %Z")


def local_stamp(value: str | None) -> str:
    """Format a stored timestamp in the local time zone.

    A timestamp that cannot be parsed is shown the way it is stored.
    """
    moment = models.safe_parse_iso(value or "")
    if moment is None:
        return value or "?"
    return format_local(moment)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """Return a count with a correctly inflected noun."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural_form or singular + 's'}"


def load_session() -> tuple[
    config.Config,
    dict[str, models.Card],
    dict[str, models.CardState],
    datetime,
] | None:
    """Load the configuration, the deck, the states and the current moment.

    None is returned and the problem is reported on stderr when the deck file
    or the state file cannot be read or holds a malformed value.
    """
    paths.ensure_dirs()
    settings = config.load_config()
    try:
        cards = models.load_deck(paths.deck_path())
        states = models.load_states(paths.state_path())
    except (ValueError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return None
    return settings, cards, states, models.now_utc()


def resolve_language(language: str | None, fallback: str) -> str | None:
    """Return the language to show first, or None when it is not supported.

    The problem is reported on stderr when the requested language is unknown.
    """
    if language is None:
        return fallback
    if language in models.SUPPORTED_LANGUAGES:
        return language
    supported = ", ".join(models.SUPPORTED_LANGUAGES)
    print(
        f"error: unknown language {language!r}, the supported languages are {supported}",
        file=sys.stderr,
    )
    return None


def report_nothing_due(
    cards: dict[str, models.Card],
    states: dict[str, models.CardState],
    moment: datetime,
) -> None:
    """Report that no card is due and name the next scheduled card."""
    upcoming = review.next_due(cards, states, moment)
    if upcoming is None:
        print("Nothing is due right now, and no card is scheduled.")
    else:
        _, when = upcoming
        print(f"Nothing is due right now. Next card at {format_local(when)}.")


def build_parser() -> argparse.ArgumentParser:
    """Build the top level argument parser."""
    parser = argparse.ArgumentParser(
        prog="linguapulse",
        description="Terminal first vocabulary trainer with spaced repetition.",
    )
    parser.add_argument("--version", action="version", version=f"linguapulse {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    show = commands.add_parser("show", help="show the card that is due")
    show.add_argument("--lang", help="language to show first when the answer is revealed")
    show.add_argument("--reveal", action="store_true", help="also print the translations")
    show.add_argument("--count", type=int, default=1, help="number of cards to show")

    next_parser = commands.add_parser("next", help="grade the card that is due")
    next_parser.add_argument("grade", choices=srs.GRADES, help="how well you knew the card")
    next_parser.add_argument("--lang", help="language to show first")
    next_parser.add_argument("--hide", action="store_true", help="do not print the translations")

    history = commands.add_parser("history", help="show the recorded reviews")
    history.add_argument("--limit", type=int, default=20, help="number of entries to show")
    history.add_argument("--card", help="only show the entries of this card")

    commands.add_parser("status", help="show the deck and the schedule")
    commands.add_parser("validate", help="check the deck file for problems")

    return parser


def command_show(args: argparse.Namespace) -> int:
    """Print the cards that are due."""
    loaded = load_session()
    if loaded is None:
        return 1
    settings, cards, states, moment = loaded
    target = resolve_language(args.lang, settings.target_lang)
    if target is None:
        return 2
    due = review.due_cards(cards, states, moment)
    if not due:
        report_nothing_due(cards, states, moment)
        return 0
    count = max(1, args.count)
    shown = due[:count]
    for index, card in enumerate(shown, start=1):
        print(
            review.render_card(
                card,
                target_lang=target,
                reveal=args.reveal,
                index=index,
                total=len(shown),
            )
        )
        print()
    return 0


def command_next(args: argparse.Namespace) -> int:
    """Grade the card that is due and record the review."""
    loaded = load_session()
    if loaded is None:
        return 1
    settings, cards, states, moment = loaded
    target = resolve_language(args.lang, settings.target_lang)
    if target is None:
        return 2
    card = review.current_card(cards, states, moment)
    if card is None:
        report_nothing_due(cards, states, moment)
        return 0
    state = states.get(card.id) or srs.new_state(card.id, moment)
    print(review.render_card(card, target_lang=target, reveal=not args.hide))
    print()
    updated = srs.apply_grade(state, args.grade, moment)
    with store.state_lock():
        current = models.load_states(paths.state_path())
        current[card.id] = updated
        models.save_states(paths.state_path(), current)
    store.append_jsonl(
        paths.history_path(),
        {
            "ts": models.iso(moment),
            "card_id": card.id,
            "grade": args.grade,
            "due": updated.due,
            "interval_days": updated.interval_days,
            "ease": updated.ease,
        },
    )
    print(f"Graded '{args.grade}'. Next review {format_local(updated.due_dt())}.")
    daemon.signal_scheduler()
    return 0


def command_history(args: argparse.Namespace) -> int:
    """Print the recorded reviews."""
    entries = store.read_jsonl(paths.history_path())
    if args.card:
        entries = [entry for entry in entries if entry.get("card_id") == args.card]
    entries = entries[-max(1, args.limit) :]
    if not entries:
        print("No reviews recorded yet.")
        return 0
    for entry in entries:
        print(
            f"{local_stamp(entry.get('ts'))}  {entry.get('card_id', '?')}  "
            f"{entry.get('grade', '?')}  -> {local_stamp(entry.get('due'))}"
        )
    return 0


def command_status(args: argparse.Namespace) -> int:
    """Print the deck, the schedule and the local configuration."""
    loaded = load_session()
    if loaded is None:
        return 1
    settings, cards, states, moment = loaded
    due = review.due_cards(cards, states, moment)
    upcoming = review.next_due(cards, states, moment)
    print(f"lingua-pulse {__version__}")
    print()
    print(f"Deck:      {plural(len(cards), 'card')}")
    print(f"Due now:   {plural(len(due), 'card')}")
    if upcoming is None:
        print("Next due:  -")
    else:
        card, when = upcoming
        print(f"Next due:  {format_local(when)}  ({card.id})")
    print(f"Languages: source {settings.source_lang}, target {settings.target_lang}")
    print(f"Time zone: {models.local_zone()}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    """Check the deck file and report every problem."""
    path = paths.deck_path()
    try:
        raw = store.read_json(path, None)
    except ValueError as error:
        print(f"problem: {error}")
        print(f"{plural(1, 'problem')} found.")
        return 1
    if raw is None:
        print(f"No deck file at {path}")
        return 1
    problems = models.validate_deck_raw(raw)
    for problem in problems:
        print(f"problem: {problem}")
    if problems:
        print(f"{plural(len(problems), 'problem')} found.")
        return 1
    try:
        cards = models.load_deck(path)
    except (ValueError, TypeError) as error:
        print(f"problem: {error}")
        print(f"{plural(1, 'problem')} found.")
        return 1
    print(f"{plural(len(cards), 'card')}, no problems found.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface and return the process exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as request:
        return int(request.code or 0)
    handlers = {
        "show": command_show,
        "next": command_next,
        "history": command_history,
        "status": command_status,
        "validate": command_validate,
    }
    return handlers[args.command](args)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -v`

Expected: PASS, 31 tests.

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/cli.py tests/test_cli.py tests/conftest.py
git commit -m "feat: add the review commands to the cli"
```

---

### Task 11: Deck Commands of the CLI

**Files:**
- Modify: `src/linguapulse/cli.py`
- Create: `src/linguapulse/seed_deck.json`
- Create: `tests/test_cli_deck.py`

**Interfaces:**
- Consumes: `config` from Task 6, `models` from Task 4, `paths` from Task 3, `srs` from Task 5, `text.normalize` from Task 2.
- Produces: `cli.command_add(args)`, `cli.command_list(args)`, `cli.command_seed(args)`, `cli.command_config(args)`, `cli.seed_cards(limit=None) -> list[models.Card]`, `cli.load_deck_and_states() -> tuple[dict[str, models.Card], dict[str, models.CardState]] | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_deck.py`:

```python
import json

from conftest import write_broken_deck
from linguapulse import cli, models, paths


def test_add_stores_a_new_card(home, capsys):
    assert cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"]) == 0
    assert "Added" in capsys.readouterr().out
    deck = models.load_deck(paths.deck_path())
    assert len(deck) == 1
    card = next(iter(deck.values()))
    assert card.translations["ar"] == "مرحبا"
    assert card.source_lang == "en"


def test_add_normalizes_the_text(home, capsys):
    assert cli.main(["add", "--term", "cafe\u0301", "--lang", "es", "--text", "hola"]) == 0
    capsys.readouterr()
    deck = models.load_deck(paths.deck_path())
    card = next(iter(deck.values()))
    assert card.term == "caf\u00e9"


def test_add_refuses_a_duplicate_card(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    assert cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert len(models.load_deck(paths.deck_path())) == 1


def test_add_rejects_mismatched_language_and_text(home, capsys):
    assert cli.main(["add", "--term", "hello", "--lang", "ar"]) == 2
    assert "--text" in capsys.readouterr().err


def test_add_creates_a_due_state(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    states = models.load_states(paths.state_path())
    assert len(states) == 1


def test_add_rejects_an_unknown_translation_language(home, capsys):
    assert cli.main(["add", "--term", "hello", "--lang", "de", "--text", "hallo"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "unknown language 'de'" in captured.err
    assert not paths.deck_path().exists()


def test_add_rejects_an_unknown_source_language(home, capsys):
    assert (
        cli.main(
            ["add", "--term", "hello", "--source-lang", "xx", "--lang", "ar", "--text", "مرحبا"]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "unknown language 'xx'" in captured.err
    assert not paths.deck_path().exists()


def test_add_rejects_an_empty_term(home, capsys):
    assert cli.main(["add", "--term", "  ", "--lang", "ar", "--text", "مرحبا"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "term" in captured.err
    assert not paths.deck_path().exists()


def test_add_rejects_an_empty_translation(home, capsys):
    assert cli.main(["add", "--term", "hello", "--lang", "ar", "--text", " "]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "translation" in captured.err
    assert not paths.deck_path().exists()


def test_add_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["add", "--term", "new", "--lang", "ar", "--text", "جديد"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""
    assert paths.deck_path().read_text(encoding="utf-8").startswith('{"version": 1, "cards": {')


def test_list_prints_the_cards(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "مرحبا" in out


def test_list_rejects_an_unknown_language(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    assert cli.main(["list", "--lang", "xx"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "unknown language 'xx'" in captured.err
    assert captured.out == ""


def test_list_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["list"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""


def test_seed_adds_the_bundled_cards(home, capsys):
    assert cli.main(["seed"]) == 0
    assert "Added" in capsys.readouterr().out
    assert len(models.load_deck(paths.deck_path())) == len(cli.seed_cards())


def test_seed_does_not_duplicate_cards(home, capsys):
    cli.main(["seed"])
    capsys.readouterr()
    assert cli.main(["seed"]) == 0
    assert "0" in capsys.readouterr().out
    assert len(models.load_deck(paths.deck_path())) == len(cli.seed_cards())


def test_seed_wakes_the_scheduler_when_it_added_cards(home, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(cli.daemon, "signal_scheduler", lambda: calls.append(True))
    assert cli.main(["seed"]) == 0
    assert calls == [True]
    capsys.readouterr()
    assert cli.main(["seed"]) == 0
    assert calls == [True]


def test_seed_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["seed"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""


def test_the_bundled_seed_cards_are_valid(home):
    for card in cli.seed_cards():
        raw = json.loads(json.dumps(card.to_dict()))
        assert models.validate_deck_raw({"cards": {card.id: raw}}) == []


def test_config_shows_the_current_settings(home, capsys):
    assert cli.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "source_lang" in out


def test_config_updates_the_settings(home, capsys):
    assert cli.main(["config", "--target-lang", "zh"]) == 0
    capsys.readouterr()
    assert cli.main(["config"]) == 0
    assert "zh" in capsys.readouterr().out


def test_config_rejects_an_unknown_language(home, capsys):
    assert cli.main(["config", "--target-lang", "zh"]) == 0
    capsys.readouterr()
    assert cli.main(["config", "--source-lang", "xx"]) == 2
    captured = capsys.readouterr()
    assert captured.err == (
        "error: unknown language 'xx', the supported languages are ar, en, es, fr, tr, zh\n"
    )
    assert captured.out == ""
    assert cli.main(["config", "--target-lang", "yy"]) == 2
    assert "unknown language 'yy'" in capsys.readouterr().err
    assert cli.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "source_lang = en" in out
    assert "target_lang = zh" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_cli_deck.py -v`

Expected: FAIL, 15 tests, because the parser does not know the `add` command yet.

- [ ] **Step 3: Write the implementation**

Create `src/linguapulse/seed_deck.json`:

```json
{
  "version": 1,
  "cards": {
    "hello": {
      "id": "hello",
      "term": "hello",
      "source_lang": "en",
      "translations": {"ar": "مرحبا", "zh": "你好"},
      "pinyin": "nǐ hǎo",
      "notes": "",
      "tags": ["greetings"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "thank-you": {
      "id": "thank-you",
      "term": "thank you",
      "source_lang": "en",
      "translations": {"ar": "شكرا", "zh": "谢谢", "es": "gracias"},
      "pinyin": "xiè xie",
      "notes": "",
      "tags": ["greetings"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "water": {
      "id": "water",
      "term": "water",
      "source_lang": "en",
      "translations": {"ar": "ماء", "zh": "水", "fr": "eau"},
      "pinyin": "shuǐ",
      "notes": "",
      "tags": ["food"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "book": {
      "id": "book",
      "term": "book",
      "source_lang": "en",
      "translations": {"ar": "كتاب", "zh": "书", "tr": "kitap"},
      "pinyin": "shū",
      "notes": "",
      "tags": ["school"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "friend": {
      "id": "friend",
      "term": "friend",
      "source_lang": "en",
      "translations": {"ar": "صديق", "zh": "朋友"},
      "pinyin": "péng you",
      "notes": "",
      "tags": ["people"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "morning": {
      "id": "morning",
      "term": "morning",
      "source_lang": "en",
      "translations": {"ar": "صباح", "zh": "早上"},
      "pinyin": "zǎo shang",
      "notes": "",
      "tags": ["time"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "house": {
      "id": "house",
      "term": "house",
      "source_lang": "en",
      "translations": {"ar": "منزل", "zh": "房子"},
      "pinyin": "fáng zi",
      "notes": "",
      "tags": ["places"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "read": {
      "id": "read",
      "term": "read",
      "source_lang": "en",
      "translations": {"ar": "يقرأ", "zh": "读"},
      "pinyin": "dú",
      "notes": "",
      "tags": ["verbs"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "eat": {
      "id": "eat",
      "term": "eat",
      "source_lang": "en",
      "translations": {"ar": "ياكل", "zh": "吃"},
      "pinyin": "chī",
      "notes": "",
      "tags": ["verbs"],
      "created_at": "2026-01-01T09:00:00+00:00"
    },
    "go": {
      "id": "go",
      "term": "go",
      "source_lang": "en",
      "translations": {"ar": "ذهب", "zh": "去"},
      "pinyin": "qù",
      "notes": "",
      "tags": ["verbs"],
      "created_at": "2026-01-01T09:00:00+00:00"
    }
  }
}
```

Extend `src/linguapulse/cli.py`.

The import header becomes:

```python
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from importlib import resources

from . import __version__, config, models, paths, review, srs, store, text
```

Add these helpers after `plural`, and make `load_session` load the deck and the states through `load_deck_and_states`, so every command that reads them reports a broken file the same way:

```python
def seed_cards(limit: int | None = None) -> list[models.Card]:
    """Return the bundled seed cards."""
    raw = (
        resources.files("linguapulse")
        .joinpath("seed_deck.json")
        .read_text(encoding="utf-8")
    )
    document = json.loads(raw)
    cards = [models.Card.from_dict(entry) for entry in document.get("cards", {}).values()]
    return cards[:limit] if limit else cards


def card_id_for(term: str) -> str:
    """Return a stable identifier for a term."""
    normalized = text.normalize(term).strip().lower()
    plain = all(
        character.isascii() and (character.isalnum() or character in "-_")
        for character in normalized
    )
    if normalized and plain:
        return normalized.replace(" ", "-")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"card-{digest}"


def load_deck_and_states() -> tuple[dict[str, models.Card], dict[str, models.CardState]] | None:
    """Load the deck and the states.

    None is returned and the problem is reported on stderr when the deck file
    or the state file cannot be read or holds a malformed value.
    """
    try:
        cards = models.load_deck(paths.deck_path())
        states = models.load_states(paths.state_path())
    except (ValueError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return None
    return cards, states
```

Register the commands in `build_parser`:

```python
    add = commands.add_parser("add", help="add a card to the deck")
    add.add_argument("--id", help="identifier of the card")
    add.add_argument("--term", required=True, help="the word to learn")
    add.add_argument("--source-lang", help="language of the term")
    add.add_argument(
        "--lang", action="append", required=True, metavar="LANG", help="language of a translation"
    )
    add.add_argument(
        "--text", action="append", required=True, metavar="TEXT", help="a translation"
    )
    add.add_argument("--pinyin", help="pinyin of the chinese translation")
    add.add_argument("--note", help="a note that is shown with the answer")
    add.add_argument("--tag", action="append", default=[], help="a tag for the card")

    listing = commands.add_parser("list", help="list the cards of the deck")
    listing.add_argument("--lang", help="only show the translation of this language")
    listing.add_argument("--limit", type=int, default=50, help="number of cards to show")

    seed = commands.add_parser("seed", help="add the bundled example cards")
    seed.add_argument("--limit", type=int, help="number of seed cards to add")

    config_parser = commands.add_parser("config", help="show or change the preferences")
    config_parser.add_argument("--source-lang", help="language of the term")
    config_parser.add_argument("--target-lang", help="language that is shown first")
    config_parser.add_argument(
        "--notify", dest="notify", action="store_true", default=None, help="enable notifications"
    )
    config_parser.add_argument(
        "--no-notify", dest="notify", action="store_false", help="disable notifications"
    )
```

Add the command implementations. `command_config` validates `--source-lang` and `--target-lang` with `resolve_language` before saving anything; `command_add`, `command_list` and `command_seed` load the deck and the states through `load_deck_and_states`, so a broken file is reported on stderr and returns 1:

```python
def command_add(args: argparse.Namespace) -> int:
    """Add one card to the deck."""
    paths.ensure_dirs()
    if len(args.lang) != len(args.text):
        print("error: every --lang needs exactly one --text", file=sys.stderr)
        return 2
    settings = config.load_config()
    source_lang = resolve_language(args.source_lang, settings.source_lang)
    if source_lang is None:
        return 2
    for language in args.lang:
        if resolve_language(language, language) is None:
            return 2
    term = text.normalize(args.term)
    if not term.strip():
        print("error: the term must not be empty", file=sys.stderr)
        return 2
    translations = {
        language: text.normalize(value) for language, value in zip(args.lang, args.text)
    }
    if any(not value.strip() for value in translations.values()):
        print("error: a translation must not be empty", file=sys.stderr)
        return 2
    loaded = load_deck_and_states()
    if loaded is None:
        return 1
    deck, _ = loaded
    card_id = args.id or card_id_for(term)
    if card_id in deck:
        print(f"error: a card with the id '{card_id}' already exists", file=sys.stderr)
        return 1
    card = models.Card(
        id=card_id,
        term=term,
        source_lang=source_lang,
        translations=translations,
        pinyin=text.normalize(args.pinyin) if args.pinyin else "",
        notes=text.normalize(args.note) if args.note else "",
        tags=list(args.tag),
        created_at=models.iso(models.now_utc()),
    )
    deck[card.id] = card
    models.save_deck(paths.deck_path(), deck)
    with store.state_lock():
        current = models.load_states(paths.state_path())
        current.setdefault(card.id, srs.new_state(card.id, models.now_utc()))
        models.save_states(paths.state_path(), current)
    print(f"Added '{card.id}' ({card.source_lang} -> {', '.join(sorted(card.translations))}).")
    daemon.signal_scheduler()
    return 0


def command_list(args: argparse.Namespace) -> int:
    """List the cards of the deck."""
    if args.lang is not None and resolve_language(args.lang, args.lang) is None:
        return 2
    paths.ensure_dirs()
    loaded = load_deck_and_states()
    if loaded is None:
        return 1
    deck, _ = loaded
    if not deck:
        print("The deck is empty. Add a card with 'linguapulse add'.")
        return 0
    for card in sorted(deck.values(), key=lambda item: item.id)[: max(1, args.limit)]:
        translations = card.translations
        if args.lang:
            translations = {args.lang: translations[args.lang]} if args.lang in translations else {}
        rendered = ", ".join(
            f"{language}: {text.isolate(value)}" for language, value in sorted(translations.items())
        )
        print(f"{card.id}: {text.isolate(card.term)}  ->  {rendered}")
    return 0


def command_seed(args: argparse.Namespace) -> int:
    """Add the bundled example cards to the deck."""
    paths.ensure_dirs()
    loaded = load_deck_and_states()
    if loaded is None:
        return 1
    deck, _ = loaded
    added: list[str] = []
    for card in seed_cards(args.limit):
        if card.id in deck:
            continue
        deck[card.id] = card
        added.append(card.id)
    if added:
        models.save_deck(paths.deck_path(), deck)
        with store.state_lock():
            current = models.load_states(paths.state_path())
            for card_id in added:
                current.setdefault(card_id, srs.new_state(card_id, models.now_utc()))
            models.save_states(paths.state_path(), current)
    print(f"Added {len(added)} seed card(s), the deck holds {len(deck)} card(s).")
    if added:
        daemon.signal_scheduler()
    return 0


def command_config(args: argparse.Namespace) -> int:
    """Show or change the preferences."""
    paths.ensure_dirs()
    settings = config.load_config()
    source = resolve_language(args.source_lang, settings.source_lang)
    if source is None:
        return 2
    target = resolve_language(args.target_lang, settings.target_lang)
    if target is None:
        return 2
    changed = False
    if args.source_lang:
        settings.source_lang = source
        changed = True
    if args.target_lang:
        settings.target_lang = target
        changed = True
    if args.notify is not None:
        settings.notify_enabled = args.notify
        changed = True
    if changed:
        config.save_config(settings)
    print(f"source_lang = {settings.source_lang}")
    print(f"target_lang = {settings.target_lang}")
    print(f"notify_enabled = {str(settings.notify_enabled).lower()}")
    return 0
```

Register the new commands in the dispatch table of `main`:

```python
    handlers = {
        "show": command_show,
        "next": command_next,
        "history": command_history,
        "status": command_status,
        "validate": command_validate,
        "add": command_add,
        "list": command_list,
        "seed": command_seed,
        "config": command_config,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_cli_deck.py -v`

Expected: PASS, 21 tests. The whole suite passes with 174 tests:

Run: `python3 -m pytest`

- [ ] **Step 5: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/cli.py src/linguapulse/seed_deck.json tests/test_cli_deck.py
git commit -m "feat: add the deck commands to the cli"
```


---

### Task 12: The Background Scheduler

**Files:**
- Create: `src/linguapulse/daemon.py`
- Modify: `src/linguapulse/cli.py`
- Create: `tests/test_daemon.py`

**Interfaces:**
- Consumes: `models` from Task 4, `notify` from Task 7, `paths` from Task 3, `scheduler` from Task 8.
- Produces: `daemon.DeliveryReport(delivered, skipped, notified, message, handled)`, `daemon.FailureLog(every=10)` with `should_log(key) -> bool` and `recovered() -> bool`, `daemon.acquire_lock(path=None)`, `daemon.write_pid(path=None)`, `daemon.read_pid(path=None) -> int | None`, `daemon.remove_pid(path=None)`, `daemon.scheduler_is_running(path=None) -> bool`, `daemon.signal_scheduler(path=None) -> bool`, `daemon.deliver_due(cards, states, moment, notifier=None, notify_enabled=True) -> DeliveryReport`, `daemon.run(max_iterations=None, idle_timeout=None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_daemon.py`:

```python
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import linguapulse
from linguapulse import cli, config, daemon, models, notify, paths, srs

PAST = "2020-01-01T09:00:00+00:00"
DUE = "2026-10-21T08:55:00+00:00"


class FakeNotifier:
    """Record the notifications that were sent."""

    def __init__(self, result=None):
        self.sent = []
        self.result = result or notify.NotifyResult(True, 0, "")

    def __call__(self, title, body):
        self.sent.append((title, body))
        return self.result


def make_card(card_id="hello"):
    return models.Card(
        id=card_id,
        term="hello",
        source_lang="en",
        translations={"ar": "مرحبا"},
        created_at=PAST,
    )


def test_a_due_card_is_delivered(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier)
    assert len(report.delivered) == 1
    assert report.notified is True
    assert len(notifier.sent) == 1
    assert "hello" in notifier.sent[0][1]


def test_the_delivered_occurrence_is_marked_as_handled(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    daemon.deliver_due(cards, states, moment, FakeNotifier())
    assert states["hello"].handled_due is not None


def test_a_card_is_not_notified_twice(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    daemon.deliver_due(cards, states, moment, notifier)
    second = daemon.deliver_due(cards, states, moment, notifier)
    assert len(notifier.sent) == 1
    assert second.delivered == ()


def test_a_stale_backlog_is_skipped(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due="2020-01-01T08:00:00+00:00")}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier)
    assert report.delivered == ()
    assert notifier.sent == []
    assert states["hello"].handled_due is not None


def test_nothing_is_due_when_the_deck_is_empty(moment):
    report = daemon.deliver_due({}, {}, moment, FakeNotifier())
    assert report.delivered == ()
    assert report.notified is False


def test_a_failing_notification_is_reported(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    failing = FakeNotifier(notify.NotifyResult(False, 1, "Could not connect"))
    report = daemon.deliver_due(cards, states, moment, failing)
    assert report.notified is False
    assert "Could not connect" in report.message
    assert states["hello"].handled_due is not None


def test_the_lock_excludes_a_second_scheduler(home):
    handle = daemon.acquire_lock()
    assert handle is not None
    assert daemon.acquire_lock() is None
    handle.close()
    second = daemon.acquire_lock()
    assert second is not None
    second.close()


def test_the_pid_file_is_written_and_removed(home):
    daemon.write_pid()
    assert daemon.read_pid() == os.getpid()
    daemon.remove_pid()
    assert daemon.read_pid() is None


def test_read_pid_ignores_a_broken_pid_file(home):
    paths_pid = daemon.paths.pid_path()
    paths_pid.write_text("not a number", encoding="utf-8")
    assert daemon.read_pid() is None


def test_read_pid_rejects_a_process_group_and_every_process(home):
    pid_file = paths.pid_path()
    for raw in ("0", "-1"):
        pid_file.write_text(f"{raw}\n", encoding="utf-8")
        assert daemon.read_pid() is None


def test_signalling_without_a_scheduler_does_nothing(home):
    assert daemon.signal_scheduler() is False


def test_signalling_a_running_scheduler_sends_a_wake_up(home):
    received = []
    previous = signal.signal(signal.SIGHUP, lambda signum, frame: received.append(signum))
    lock = daemon.acquire_lock()
    try:
        daemon.write_pid()
        assert daemon.signal_scheduler() is True
    finally:
        signal.signal(signal.SIGHUP, previous)
        lock.close()
    assert received == [signal.SIGHUP]


def test_a_stale_pid_file_without_the_lock_is_not_signalled(home):
    received = []
    previous = signal.signal(signal.SIGHUP, lambda signum, frame: received.append(signum))
    try:
        daemon.write_pid()
        assert daemon.scheduler_is_running() is False
        assert daemon.signal_scheduler() is False
    finally:
        signal.signal(signal.SIGHUP, previous)
    assert received == []


def test_the_failure_log_reports_the_first_and_every_tenth_failure():
    failures = daemon.FailureLog(every=10)
    assert failures.should_log("boom") is True
    assert failures.should_log("boom") is False
    for _ in range(7):
        failures.should_log("boom")
    assert failures.should_log("boom") is True


def test_the_failure_log_reports_the_recovery():
    failures = daemon.FailureLog(every=10)
    assert failures.recovered() is False
    failures.should_log("boom")
    assert failures.recovered() is True
    assert failures.recovered() is False
    assert failures.should_log("boom") is True


def test_the_loop_stops_after_the_configured_number_of_iterations(home):
    assert daemon.run(max_iterations=2, idle_timeout=0.0) == 0


def test_a_grade_saved_while_sending_survives_the_marks(home, moment, monkeypatch):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    graded = {}

    def grade_while_sending(title, body):
        states = models.load_states(paths.state_path())
        graded["state"] = srs.apply_grade(states["hello"], "easy", moment)
        models.save_states(paths.state_path(), {"hello": graded["state"]})
        return notify.NotifyResult(True, 0, "")

    monkeypatch.setattr(daemon.notify, "send", grade_while_sending)
    assert daemon.run(max_iterations=1, idle_timeout=0.0) == 0
    saved = models.load_states(paths.state_path())["hello"]
    assert saved.reps == graded["state"].reps
    assert saved.interval_days == graded["state"].interval_days
    assert saved.ease == graded["state"].ease
    assert saved.handled_due == due


def test_a_cli_grade_saved_while_sending_survives_the_marks(home, monkeypatch):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    graded = {}

    def grade_while_sending(title, body):
        assert cli.main(["next", "good"]) == 0
        graded["state"] = models.load_states(paths.state_path())["hello"]
        return notify.NotifyResult(True, 0, "")

    monkeypatch.setattr(daemon.notify, "send", grade_while_sending)
    assert daemon.run(max_iterations=1, idle_timeout=0.0) == 0
    saved = models.load_states(paths.state_path())["hello"]
    assert saved.reps == graded["state"].reps == 1
    assert saved.interval_days == graded["state"].interval_days
    assert saved.ease == graded["state"].ease
    assert saved.handled_due == due


def test_due_reminders_are_marked_when_notifications_are_disabled(home, monkeypatch, capsys):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    config.save_config(config.Config(notify_enabled=False))
    sent = []
    monkeypatch.setattr(daemon.notify, "send", lambda title, body: sent.append(title))
    assert daemon.run(max_iterations=1, idle_timeout=0.0) == 0
    assert sent == []
    assert models.load_states(paths.state_path())["hello"].handled_due == due
    captured = capsys.readouterr()
    assert "notifications are disabled" in captured.err
    assert "notification problem" not in captured.err


def test_the_loop_sleeps_until_the_next_wakeup(home, monkeypatch):
    fixed = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(models, "now_utc", lambda: fixed)
    due = models.iso(fixed + timedelta(hours=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    timeouts = []

    def fake_select(read, write, error, timeout):
        timeouts.append(timeout)
        return ([], [], [])

    monkeypatch.setattr(daemon.select, "select", fake_select)
    assert daemon.run(max_iterations=1) == 0
    assert timeouts == [3600.0]


def test_a_notification_problem_and_the_recovery_are_logged(home, monkeypatch, capsys):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    calls = []

    def flaky(title, body):
        calls.append(title)
        if len(calls) == 1:
            models.save_deck(
                paths.deck_path(), {"hello": make_card(), "world": make_card("world")}
            )
            models.save_states(
                paths.state_path(),
                {
                    "hello": models.CardState(card_id="hello", due=due),
                    "world": models.CardState(card_id="world", due=due),
                },
            )
            return notify.NotifyResult(False, 1, "Could not connect")
        return notify.NotifyResult(True, 0, "")

    monkeypatch.setattr(daemon.notify, "send", flaky)
    assert daemon.run(max_iterations=2, idle_timeout=0.0) == 0
    assert len(calls) == 2
    captured = capsys.readouterr()
    assert "notification problem: Could not connect" in captured.err
    assert "notifications are being delivered again" in captured.err


def test_a_broken_deck_does_not_kill_the_scheduler(home, capsys):
    paths.deck_path().write_text('{"version": 1, "cards": {', encoding="utf-8")
    assert daemon.run(max_iterations=2, idle_timeout=0.0) == 0
    captured = capsys.readouterr()
    assert "error: " in captured.err
    assert "is not valid JSON" in captured.err
    assert daemon.read_pid() is None
    lock = daemon.acquire_lock()
    assert lock is not None
    lock.close()


def test_a_second_scheduler_reports_the_error(home, capsys):
    lock = daemon.acquire_lock()
    try:
        assert daemon.run(max_iterations=1, idle_timeout=0.0) == 1
    finally:
        lock.close()
    assert "error: another scheduler is already running" in capsys.readouterr().err


def test_the_scheduler_stops_on_a_terminate_signal(home):
    source_root = str(Path(linguapulse.__file__).resolve().parents[1])
    environment = {**os.environ, "PYTHONPATH": source_root}
    process = subprocess.Popen(
        [sys.executable, "-m", "linguapulse", "daemon"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and daemon.read_pid() is None:
            time.sleep(0.1)
        assert daemon.read_pid() == process.pid
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=10) == 0
        assert daemon.read_pid() is None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
```

Add the `moment` fixture to `tests/conftest.py`:

```python
@pytest.fixture()
def moment():
    """Return a fixed point in time for the scheduler tests."""
    return datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
```

and add these imports at the top of `tests/conftest.py`:

```python
from datetime import datetime, timezone
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_daemon.py -v`

Expected: FAIL with `ImportError: cannot import name 'daemon' from 'linguapulse'`, the module does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `src/linguapulse/daemon.py`:

```python
"""The background scheduler that wakes up when a card becomes due."""

from __future__ import annotations

import errno
import fcntl
import io
import os
import select
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import config, models, notify, paths, scheduler, store

RESCAN_SECONDS = 3600.0


@dataclass(frozen=True)
class DeliveryReport:
    """The outcome of one delivery round."""

    delivered: tuple[scheduler.Occurrence, ...]
    skipped: tuple[scheduler.Occurrence, ...]
    notified: bool
    message: str
    handled: tuple[tuple[str, str], ...] = ()


class FailureLog:
    """Report a failure once and then only every tenth repetition."""

    def __init__(self, every: int = 10) -> None:
        self.every = max(1, every)
        self.counts: dict[str, int] = {}
        self.current = ""

    def should_log(self, key: str) -> bool:
        """Return True when the failure should be written to the log."""
        self.current = key
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return count == 1 or count % self.every == 0

    def recovered(self) -> bool:
        """Forget the failure streak and return True when there was one."""
        if not self.current:
            return False
        self.current = ""
        self.counts.clear()
        return True


def acquire_lock(path: Path | None = None) -> io.TextIOWrapper | None:
    """Take the exclusive scheduler lock, or return None when it is taken."""
    target = path or paths.lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = open(target, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return None
        raise
    return handle


def write_pid(path: Path | None = None) -> None:
    """Write the process id of the scheduler to the pid file."""
    target = path or paths.pid_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{os.getpid()}\n", encoding="utf-8")


def read_pid(path: Path | None = None) -> int | None:
    """Read the process id of the scheduler, or None when there is none."""
    target = path or paths.pid_path()
    try:
        raw = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 1 else None


def remove_pid(path: Path | None = None) -> None:
    """Remove the pid file of the scheduler."""
    target = path or paths.pid_path()
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def _lock_is_free(path: Path | None = None) -> bool:
    """Return True when no scheduler holds the lock, releasing it again."""
    target = None if path is None else path.parent / "daemon.lock"
    handle = acquire_lock(target)
    if handle is None:
        return False
    handle.close()
    return True


def _pid_is_alive(pid: int) -> bool:
    """Return True when a process with this id still exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def scheduler_is_running(path: Path | None = None) -> bool:
    """Return True when a scheduler holds the lock and its process is alive."""
    if _lock_is_free(path):
        return False
    pid = read_pid(path)
    return pid is not None and _pid_is_alive(pid)


def signal_scheduler(path: Path | None = None) -> bool:
    """Ask a running scheduler to recompute its next wake up."""
    if _lock_is_free(path):
        return False
    pid = read_pid(path)
    if pid is None or not _pid_is_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGHUP)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _notification_for(group: Sequence[scheduler.Occurrence]) -> tuple[str, str]:
    """Build the title and the body of one notification."""
    lines: list[str] = []
    for occurrence in group:
        card = occurrence.card
        translations = card.translations
        answer = ""
        if translations:
            language = sorted(translations)[0]
            answer = f"  {language}: {translations[language]}"
        lines.append(f"{card.term}{answer}")
    if len(group) == 1:
        title = "lingua-pulse: a card is due"
    else:
        title = f"lingua-pulse: {len(group)} cards are due"
    return title, "\n".join(lines)


def _mark_handled(
    states: Mapping[str, models.CardState],
    occurrences: Sequence[scheduler.Occurrence],
) -> tuple[tuple[str, str], ...]:
    """Remember that these occurrences were acted on and return their marks."""
    marks: list[tuple[str, str]] = []
    for occurrence in occurrences:
        state = occurrence.state
        if state is None:
            continue
        mark = (occurrence.card.id, occurrence.due.isoformat())
        marks.append(mark)
        state.handled_due = mark[1]
    return tuple(marks)


def _save_marks(marks: Sequence[tuple[str, str]]) -> dict[str, models.CardState]:
    """Apply the handled marks to the current state file and save it.

    The states are read again right before the write, because a grade may
    have been recorded while the notification was being sent. Only the marks
    are applied, so the grade keeps its own due, interval and ease.
    """
    with store.state_lock():
        states = models.load_states(paths.state_path())
        for card_id, due_iso in marks:
            state = states.setdefault(card_id, models.CardState(card_id=card_id, due=due_iso))
            state.handled_due = due_iso
        models.save_states(paths.state_path(), states)
    return states


def deliver_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
    notifier: Callable[[str, str], notify.NotifyResult] | None = None,
    notify_enabled: bool = True,
) -> DeliveryReport:
    """Deliver the reminder that is due and remember that it was handled.

    The message of the report is only set when something went wrong, so that
    the caller can log it without writing a line for every empty round. The
    handled marks are returned for the caller to persist, because the states
    it read may be out of date by the time the notification was sent. When
    notifications are disabled the due occurrences are marked as handled
    without sending anything.
    """
    send = notifier or notify.send
    pending = scheduler.pending_occurrences(cards, states, moment)
    if not pending:
        return DeliveryReport((), (), False, "")
    reminder = scheduler.plan_reminder(pending, moment)
    if reminder is None:
        return DeliveryReport((), (), False, "")
    if not reminder.group:
        marks = _mark_handled(states, reminder.skipped)
        return DeliveryReport((), reminder.skipped, False, "", marks)
    if not notify_enabled:
        marks = _mark_handled(states, reminder.handled)
        return DeliveryReport((), (), False, "", marks)
    title, body = _notification_for(reminder.group)
    result = send(title, body)
    marks = _mark_handled(states, reminder.handled)
    if result.ok:
        return DeliveryReport(reminder.group, reminder.skipped, True, "", marks)
    return DeliveryReport(
        reminder.group,
        reminder.skipped,
        False,
        result.message or "the notification failed",
        marks,
    )


def run(max_iterations: int | None = None, idle_timeout: float | None = None) -> int:
    """Run the scheduler until it is stopped.

    The scheduler sleeps until the exact moment the next card is due. When
    nothing is scheduled it rescans the files once an hour, that is the
    safety net for a deck that was edited by hand. The optional idle timeout
    caps that sleep, it is only used by the tests.
    """
    paths.ensure_dirs()
    lock = acquire_lock()
    if lock is None:
        print("error: another scheduler is already running", file=sys.stderr)
        return 1
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    failures = FailureLog()
    stop_signals: list[int] = []
    wake_signals: list[int] = []

    def handle_stop(signum: int, frame: object) -> None:
        stop_signals.append(signum)
        try:
            os.write(write_fd, b"x")
        except OSError:
            pass

    def handle_wake(signum: int, frame: object) -> None:
        wake_signals.append(signum)
        try:
            os.write(write_fd, b"x")
        except OSError:
            pass

    previous = {
        signal.SIGTERM: signal.signal(signal.SIGTERM, handle_stop),
        signal.SIGINT: signal.signal(signal.SIGINT, handle_stop),
        signal.SIGHUP: signal.signal(signal.SIGHUP, handle_wake),
    }
    iterations = 0
    try:
        write_pid()
        disabled_notice = False
        while not stop_signals:
            timeout = RESCAN_SECONDS
            try:
                settings = config.load_config()
                cards = models.load_deck(paths.deck_path())
                states = models.load_states(paths.state_path())
                moment = models.now_utc()
                report = deliver_due(
                    cards,
                    states,
                    moment,
                    notify_enabled=settings.notify_enabled,
                )
                if report.handled:
                    states = _save_marks(report.handled)
                if not settings.notify_enabled:
                    if report.handled and not disabled_notice:
                        print(
                            "notifications are disabled, marking due reminders as handled",
                            file=sys.stderr,
                            flush=True,
                        )
                        disabled_notice = True
                else:
                    disabled_notice = False
                    if report.delivered:
                        print(f"delivered {len(report.delivered)} reminder(s)", flush=True)
                    elif report.skipped:
                        print(f"skipped {len(report.skipped)} stale reminder(s)", flush=True)
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
                next_at = scheduler.next_wakeup(cards, states, models.now_utc())
                if next_at is not None:
                    timeout = max(0.0, (next_at - models.now_utc()).total_seconds())
            except (ValueError, TypeError, OSError) as error:
                if failures.should_log(f"round failed: {error}"):
                    print(f"error: {error}", file=sys.stderr, flush=True)
            if idle_timeout is not None:
                timeout = idle_timeout
            select.select([read_fd], [], [], timeout)
            try:
                os.read(read_fd, 4096)
            except (BlockingIOError, OSError):
                pass
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        remove_pid()
        os.close(read_fd)
        os.close(write_fd)
        lock.close()
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_daemon.py -v`

Expected: PASS, 24 tests.

- [ ] **Step 5: Wire the CLI to the scheduler**

In `src/linguapulse/cli.py`:

Add `daemon` to the package imports, so that the line reads:

```python
from . import __version__, config, daemon, models, paths, review, srs, store, text
```

At the end of `command_next`, right before `return 0`, add:

```python
    daemon.signal_scheduler()
```

At the end of `command_add`, right before `return 0`, add:

```python
    daemon.signal_scheduler()
```

- [ ] **Step 6: Register the daemon command**

In `build_parser` of `src/linguapulse/cli.py`, add:

```python
    commands.add_parser("daemon", help="run the scheduler in the foreground")
```

In `main` of `src/linguapulse/cli.py`, add the import of the handler and the dispatch entry:

```python
def command_daemon(args: argparse.Namespace) -> int:
    """Run the scheduler in the foreground."""
    return daemon.run()
```

```python
        "daemon": command_daemon,
```

- [ ] **Step 7: Run the whole test suite**

Run: `python3 -m pytest -v`

Expected: PASS, 198 tests, every test of every task.

- [ ] **Step 8: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/daemon.py src/linguapulse/cli.py tests/test_daemon.py tests/conftest.py
git commit -m "feat: add the background scheduler that wakes up when a card is due"
```

---

### Task 13: Diagnostics and the Doctor Command

**Files:**
- Create: `src/linguapulse/diagnostics.py`
- Modify: `src/linguapulse/cli.py`
- Create: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `config` from Task 6, `daemon` from Task 12, `models` from Task 4, `notify` from Task 7, `paths` from Task 3, `scheduler` from Task 8.
- Produces: `diagnostics.Check(name, ok, detail)`, `diagnostics.check_paths()`, `diagnostics.check_config()`, `diagnostics.check_deck()`, `diagnostics.check_state()`, `diagnostics.check_notify_send()`, `diagnostics.check_busctl()`, `diagnostics.check_session_bus()`, `diagnostics.check_notification_daemon()`, `diagnostics.check_scheduler()`, `diagnostics.check_schedule()`, `diagnostics.run_checks() -> list[Check]`, `diagnostics.NOTIFICATION_HELP`, `cli.command_doctor(args)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_diagnostics.py`:

```python
import os

import pytest

from linguapulse import __version__, cli, config, daemon, diagnostics, notify, paths, store

PAST = "2020-01-01T09:00:00+00:00"
FUTURE = "2099-01-01T09:00:00+00:00"


def isolate_notifications(monkeypatch):
    """Keep a check that runs everything away from the notification bus."""
    monkeypatch.setattr(notify, "notify_send_path", lambda env=None: "/usr/bin/notify-send")
    monkeypatch.setattr(
        notify, "session_bus_address", lambda env=None: "unix:path=/run/user/1000/bus"
    )
    monkeypatch.setattr(notify, "notification_daemon", lambda env=None: "dunst")
    monkeypatch.setattr(
        diagnostics.shutil, "which", lambda name, path=None: "/usr/bin/busctl"
    )


def test_a_check_reports_its_name_and_detail():
    check = diagnostics.Check("deck", True, "3 cards")
    assert check.ok is True
    assert check.detail == "3 cards"


def test_the_paths_are_reported_as_ready(home):
    check = diagnostics.check_paths()
    assert check.ok is True


def test_the_deck_check_reports_the_number_of_cards(home):
    check = diagnostics.check_deck()
    assert check.ok is True
    assert "0 cards" in check.detail


def test_the_deck_check_fails_on_a_broken_deck(home):
    store.write_json(
        paths.deck_path(),
        {"cards": {"broken": {"id": "broken", "term": "", "source_lang": "en"}}},
    )
    check = diagnostics.check_deck()
    assert check.ok is False


def test_the_notify_send_check_reports_a_missing_binary(monkeypatch):
    monkeypatch.setattr(notify, "notify_send_path", lambda env=None: None)
    check = diagnostics.check_notify_send()
    assert check.ok is False
    assert "notify-send" in check.detail


def test_the_notify_send_check_reports_an_installed_binary(monkeypatch):
    monkeypatch.setattr(notify, "notify_send_path", lambda env=None: "/usr/bin/notify-send")
    check = diagnostics.check_notify_send()
    assert check.ok is True


def test_the_session_bus_check_reports_a_missing_address(monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "")
    check = diagnostics.check_session_bus()
    assert check.ok is False


def test_the_notification_daemon_check_reports_a_running_daemon(monkeypatch):
    monkeypatch.setattr(notify, "notification_daemon", lambda env=None: "dunst")
    check = diagnostics.check_notification_daemon()
    assert check.ok is True
    assert "dunst" in check.detail


def test_the_scheduler_check_reports_a_running_scheduler(home):
    lock = daemon.acquire_lock()
    try:
        daemon.write_pid()
        check = diagnostics.check_scheduler()
        assert check.ok is True
    finally:
        lock.close()


def test_the_scheduler_check_reports_a_missing_scheduler(home):
    check = diagnostics.check_scheduler()
    assert check.ok is False


def test_every_check_has_a_name_and_a_detail(home, monkeypatch):
    isolate_notifications(monkeypatch)
    for check in diagnostics.run_checks():
        assert check.name
        assert check.detail


def test_run_checks_covers_the_installation(home, monkeypatch):
    isolate_notifications(monkeypatch)
    names = [check.name for check in diagnostics.run_checks()]
    assert names == [
        "paths",
        "config",
        "deck",
        "state",
        "notify-send",
        "busctl",
        "session bus",
        "notification daemon",
        "scheduler",
        "schedule",
    ]


def test_the_paths_check_reports_an_unwritable_directory(home, monkeypatch):
    def fail():
        raise OSError("permission denied")

    monkeypatch.setattr(paths, "ensure_dirs", fail)
    check = diagnostics.check_paths()
    assert check.ok is False
    assert "permission denied" in check.detail


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_the_paths_check_reports_a_read_only_directory(home):
    directory = paths.data_dir()
    directory.chmod(0o555)
    try:
        check = diagnostics.check_paths()
    finally:
        directory.chmod(0o755)
    assert check.ok is False
    assert str(directory) in check.detail
    assert "not writable" in check.detail


def test_the_deck_check_reports_a_file_that_is_not_json(home):
    paths.deck_path().write_text("{", encoding="utf-8")
    check = diagnostics.check_deck()
    assert check.ok is False
    assert "cannot be read" in check.detail


def test_the_state_check_reports_an_empty_state(home):
    check = diagnostics.check_state()
    assert check.ok is True
    assert "0 states" in check.detail


def test_the_state_check_reports_the_scheduled_cards(home):
    store.write_json(
        paths.state_path(),
        {"cards": {"hello": {"card_id": "hello", "due": FUTURE}}},
    )
    check = diagnostics.check_state()
    assert check.ok is True
    assert "1 state" in check.detail


def test_the_state_check_fails_on_a_broken_state_file(home):
    paths.state_path().write_text("{", encoding="utf-8")
    check = diagnostics.check_state()
    assert check.ok is False
    assert "cannot be read" in check.detail


def test_the_busctl_check_reports_a_missing_binary(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: None)
    check = diagnostics.check_busctl()
    assert check.ok is False
    assert "busctl" in check.detail


def test_the_busctl_check_reports_an_installed_binary(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: "/usr/bin/busctl")
    check = diagnostics.check_busctl()
    assert check.ok is True
    assert "/usr/bin/busctl" in check.detail


def test_the_notification_daemon_check_reports_an_unowned_bus_name(monkeypatch):
    monkeypatch.setattr(notify, "notification_daemon", lambda env=None: "-")
    check = diagnostics.check_notification_daemon()
    assert check.ok is False
    assert "no daemon" in check.detail


def test_the_config_check_reports_the_defaults(home):
    check = diagnostics.check_config()
    assert check.ok is True
    assert "defaults" in check.detail
    assert "source en" in check.detail
    assert "target ar" in check.detail


def test_the_config_check_reports_the_effective_file(home):
    config.save_config(config.Config(source_lang="fr", target_lang="zh", notify_enabled=False))
    check = diagnostics.check_config()
    assert check.ok is True
    assert "source fr" in check.detail
    assert "target zh" in check.detail
    assert "notifications disabled" in check.detail


def test_the_config_check_surfaces_a_rejected_file(home):
    paths.config_path().write_text("{", encoding="utf-8")
    check = diagnostics.check_config()
    assert check.ok is False
    assert "not valid JSON" in check.detail
    assert "defaults" in check.detail


def test_the_config_check_surfaces_a_rejected_value(home):
    store.write_json(paths.config_path(), {"source_lang": "de", "target_lang": "ar"})
    check = diagnostics.check_config()
    assert check.ok is False
    assert "source_lang 'de'" in check.detail
    assert "source en" in check.detail


def test_the_scheduler_check_reports_a_dead_process(home, monkeypatch):
    daemon.write_pid()
    monkeypatch.setattr(daemon, "scheduler_is_running", lambda path=None: False)
    check = diagnostics.check_scheduler()
    assert check.ok is False
    assert "not running" in check.detail


def test_the_schedule_check_reports_nothing_scheduled(home):
    check = diagnostics.check_schedule()
    assert check.ok is True
    assert "nothing is scheduled" in check.detail


def test_the_schedule_check_reports_the_next_wakeup(home):
    store.write_json(
        paths.deck_path(),
        {
            "cards": {
                "hello": {
                    "id": "hello",
                    "term": "hello",
                    "source_lang": "en",
                    "translations": {"ar": "مرحبا"},
                    "created_at": PAST,
                }
            }
        },
    )
    store.write_json(
        paths.state_path(),
        {"cards": {"hello": {"card_id": "hello", "due": FUTURE}}},
    )
    check = diagnostics.check_schedule()
    assert check.ok is True
    assert "next wakeup" in check.detail
    assert "2099" in check.detail


def test_the_schedule_check_reports_a_due_card(home):
    store.write_json(
        paths.deck_path(),
        {
            "cards": {
                "hello": {
                    "id": "hello",
                    "term": "hello",
                    "source_lang": "en",
                    "translations": {"ar": "مرحبا"},
                    "created_at": PAST,
                }
            }
        },
    )
    store.write_json(
        paths.state_path(),
        {"cards": {"hello": {"card_id": "hello", "due": PAST}}},
    )
    check = diagnostics.check_schedule()
    assert check.ok is True
    assert "due now" in check.detail


def test_the_doctor_prints_the_version_and_the_checks(monkeypatch, capsys):
    monkeypatch.setattr(
        diagnostics, "run_checks", lambda: [diagnostics.Check("deck", True, "3 cards")]
    )
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert f"lingua-pulse {__version__}" in out
    assert "[ok] deck: 3 cards" in out


def test_the_doctor_exits_with_one_when_a_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        diagnostics,
        "run_checks",
        lambda: [diagnostics.Check("scheduler", False, "not running")],
    )
    assert cli.main(["doctor"]) == 1
    assert "[FAIL] scheduler: not running" in capsys.readouterr().out


def test_the_doctor_explains_how_to_diagnose_a_notification_failure(monkeypatch, capsys):
    monkeypatch.setattr(diagnostics, "run_checks", lambda: [])
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "notify-send" in out
    assert "busctl" in out
    assert "DBUS_SESSION_BUS_ADDRESS" in out


def test_status_reports_the_notifications_and_the_scheduler(home, capsys, monkeypatch):
    monkeypatch.setattr(daemon, "scheduler_is_running", lambda path=None: False)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Notify:     enabled" in out
    assert "Scheduler: not running" in out


def test_status_reports_disabled_notifications_and_a_running_scheduler(home, capsys, monkeypatch):
    config.save_config(config.Config(notify_enabled=False))
    monkeypatch.setattr(daemon, "scheduler_is_running", lambda path=None: True)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Notify:     disabled" in out
    assert "Scheduler: running" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_diagnostics.py -v`

Expected: FAIL with `ImportError: cannot import name 'diagnostics' from 'linguapulse'`.

- [ ] **Step 3: Write the implementation**

Create `src/linguapulse/diagnostics.py`:

```python
"""Checks that tell the user whether the installation works."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config, daemon, models, notify, paths, scheduler, store

NOTIFICATION_HELP = (
    "run 'notify-send --app-name=linguapulse test hello' to test the notification itself",
    "run 'busctl --user --no-pager list | grep org.freedesktop.Notifications' to find the daemon",
    "in a systemd user service, make sure DBUS_SESSION_BUS_ADDRESS reaches the scheduler",
)


@dataclass(frozen=True)
class Check:
    """The result of one diagnostic check."""

    name: str
    ok: bool
    detail: str


def _counted(count: int, singular: str) -> str:
    """Return a count with a correctly inflected noun."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {singular}s"


def _probe_writable(directory: Path) -> None:
    """Write and remove a probe file to prove that the directory is writable."""
    descriptor, name = tempfile.mkstemp(
        dir=directory, prefix=".linguapulse-probe-", suffix=".tmp"
    )
    try:
        os.write(descriptor, b"probe\n")
    finally:
        os.close(descriptor)
        Path(name).unlink(missing_ok=True)


def check_paths() -> Check:
    """Check that the data directories exist and are writable."""
    try:
        paths.ensure_dirs()
    except OSError as exc:
        return Check("paths", False, f"the data directory is not writable: {exc}")
    directories = (paths.data_dir(), paths.config_dir(), paths.state_dir())
    for directory in directories:
        try:
            _probe_writable(directory)
        except OSError as exc:
            return Check("paths", False, f"{directory} is not writable: {exc}")
    return Check(
        "paths",
        True,
        f"data {directories[0]}, config {directories[1]}, state {directories[2]}",
    )


def _config_summary(settings: config.Config) -> str:
    """Describe the configuration that is in effect."""
    notifications = "enabled" if settings.notify_enabled else "disabled"
    return (
        f"source {settings.source_lang}, target {settings.target_lang}, "
        f"notifications {notifications}"
    )


def _rejected_config_fields(raw: dict[str, object], settings: config.Config) -> list[str]:
    """Return the fields of the file that the loader replaced with a default."""
    rejected: list[str] = []
    for field_name, attribute in (
        ("source_lang", settings.source_lang),
        ("target_lang", settings.target_lang),
    ):
        if field_name not in raw:
            continue
        value = raw[field_name]
        if not isinstance(value, str) or value.strip() != attribute:
            rejected.append(f"{field_name} {value!r}")
    if "notify_enabled" in raw:
        value = raw["notify_enabled"]
        if not isinstance(value, bool) or value != settings.notify_enabled:
            rejected.append(f"notify_enabled {value!r}")
    return rejected


def check_config() -> Check:
    """Check which configuration is in effect and whether the file was accepted."""
    defaults = _config_summary(config.Config())
    try:
        raw = store.read_json(paths.config_path(), None)
    except (OSError, ValueError) as exc:
        return Check(
            "config",
            False,
            f"the configuration file cannot be read: {exc}; the defaults are in effect: {defaults}",
        )
    if raw is None:
        return Check("config", True, f"the defaults are in effect: {defaults}")
    if not isinstance(raw, dict):
        return Check(
            "config",
            False,
            f"the configuration file is not a JSON object; the defaults are in effect: {defaults}",
        )
    settings = config.Config.from_dict(raw)
    rejected = _rejected_config_fields(raw, settings)
    if rejected:
        return Check(
            "config",
            False,
            f"{', '.join(rejected)} rejected; in effect: {_config_summary(settings)}",
        )
    return Check("config", True, f"in effect: {_config_summary(settings)}")


def check_deck() -> Check:
    """Check that the deck file can be read and has no problems."""
    path = paths.deck_path()
    try:
        raw = store.read_json(path, None)
    except (OSError, ValueError) as exc:
        return Check("deck", False, f"the deck file cannot be read: {exc}")
    if raw is None:
        return Check("deck", True, "0 cards, no deck file yet")
    problems = models.validate_deck_raw(raw)
    if problems:
        return Check("deck", False, f"{len(problems)} problem(s): {problems[0]}")
    count = len(raw.get("cards", {})) if isinstance(raw, dict) else 0
    return Check("deck", True, f"{count} cards, no problems")


def check_state() -> Check:
    """Check that the state file can be read and holds a schedule."""
    path = paths.state_path()
    try:
        states = models.load_states(path)
    except (OSError, TypeError, ValueError) as exc:
        return Check("state", False, f"the state file cannot be read: {exc}")
    if not path.exists():
        return Check("state", True, "0 states, no state file yet")
    return Check("state", True, f"{_counted(len(states), 'state')}, no problems")


def check_notify_send() -> Check:
    """Check that notify-send is installed."""
    binary = notify.notify_send_path()
    if binary is None:
        return Check("notify-send", False, "notify-send was not found in PATH")
    return Check("notify-send", True, binary)


def check_busctl() -> Check:
    """Check that busctl is installed, so that the daemon can be identified."""
    binary = shutil.which(notify.BUSCTL, path=os.environ.get("PATH") or "")
    if binary is None:
        return Check("busctl", False, "busctl was not found in PATH")
    return Check("busctl", True, binary)


def check_session_bus() -> Check:
    """Check that a session bus address can be resolved."""
    address = notify.session_bus_address()
    if address is None:
        return Check(
            "session bus",
            False,
            "no DBUS_SESSION_BUS_ADDRESS and no XDG_RUNTIME_DIR",
        )
    return Check("session bus", True, address)


def check_notification_daemon() -> Check:
    """Check that a notification daemon owns the notifications bus name."""
    daemon_name = notify.notification_daemon()
    if daemon_name is None or daemon_name == "-":
        return Check(
            "notification daemon",
            False,
            "no daemon owns org.freedesktop.Notifications",
        )
    return Check("notification daemon", True, daemon_name)


def check_scheduler() -> Check:
    """Check that the scheduler is running."""
    pid = daemon.read_pid()
    if pid is None:
        return Check("scheduler", False, "the scheduler is not running")
    if not daemon.scheduler_is_running():
        return Check("scheduler", False, f"the scheduler is not running (process {pid} is gone)")
    return Check("scheduler", True, f"running with process {pid}")


def check_schedule() -> Check:
    """Check when the scheduler will wake up next."""
    try:
        cards = models.load_deck(paths.deck_path())
        states = models.load_states(paths.state_path())
    except (OSError, TypeError, ValueError) as exc:
        return Check("schedule", False, f"the deck or state file cannot be read: {exc}")
    moment = models.now_utc()
    pending = scheduler.pending_occurrences(cards, states, moment)
    if pending:
        return Check("schedule", True, f"{_counted(len(pending), 'card')} due now")
    upcoming = scheduler.next_wakeup(cards, states, moment)
    if upcoming is None:
        return Check("schedule", True, "nothing is scheduled")
    return Check("schedule", True, f"next wakeup at {upcoming.isoformat()}")


def run_checks() -> list[Check]:
    """Run every diagnostic check."""
    return [
        check_paths(),
        check_config(),
        check_deck(),
        check_state(),
        check_notify_send(),
        check_busctl(),
        check_session_bus(),
        check_notification_daemon(),
        check_scheduler(),
        check_schedule(),
    ]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_diagnostics.py -v`

Expected: PASS, 34 tests.

- [ ] **Step 5: Add the doctor command**

In `src/linguapulse/cli.py`, add `diagnostics` to the package imports, so that the line reads:

```python
from . import __version__, config, daemon, diagnostics, models, paths, review, srs, store, text
```

In `build_parser`, add:

```python
    commands.add_parser("doctor", help="check the installation")
```

Add the command implementation:

```python
def command_doctor(args: argparse.Namespace) -> int:
    """Run every diagnostic check and report the result."""
    print(f"lingua-pulse {__version__}")
    print()
    failed = 0
    for check in diagnostics.run_checks():
        mark = "ok" if check.ok else "FAIL"
        print(f"[{mark}] {check.name}: {check.detail}")
        if not check.ok:
            failed += 1
    print()
    print("To diagnose a notification failure:")
    for line in diagnostics.NOTIFICATION_HELP:
        print(f"  {line}")
    return 1 if failed else 0
```

Add the dispatch entry:

```python
        "doctor": command_doctor,
```

- [ ] **Step 6: Extend the status command**

In `command_status` of `src/linguapulse/cli.py`, add these lines before the final `return 0`:

```python
    print(f"Notify:     {'enabled' if settings.notify_enabled else 'disabled'}")
    print(f"Scheduler: {'running' if daemon.scheduler_is_running() else 'not running'}")
```

- [ ] **Step 7: Run the whole test suite**

Run: `python3 -m pytest -v`

Expected: PASS, 232 tests, every test of every task.

- [ ] **Step 8: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/diagnostics.py src/linguapulse/cli.py tests/test_diagnostics.py
git commit -m "feat: add diagnostics and the doctor command"
```


---

### Task 14: Installing the Service and the Autostart

**Files:**
- Create: `src/linguapulse/service.py`
- Modify: `src/linguapulse/cli.py`
- Create: `tests/test_service.py`

**Interfaces:**
- Consumes: `paths` from Task 3.
- Produces: `service.UNIT_NAME`, `service.AUTOSTART_BEGIN`, `service.AUTOSTART_END`, `service.unit_path() -> Path`, `service.autostart_path() -> Path`, `service.render_unit(executable) -> str`, `service.install_unit(executable) -> Path`, `service.remove_unit() -> bool`, `service.autostart_block() -> str`, `service.install_autostart() -> bool`, `service.remove_autostart() -> bool`, `service.enable() -> bool`, `service.disable() -> bool`, `service.default_executable() -> str`, `service.install(executable) -> list[str]`, `service.uninstall() -> list[str]`, `cli.command_install(args)`, `cli.command_uninstall(args)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_service.py`:

```python
import pytest

from linguapulse import cli, service


def test_render_unit_contains_the_exec_start():
    unit = service.render_unit("/usr/local/bin/linguapulse")
    assert "ExecStart=/usr/local/bin/linguapulse daemon" in unit


def test_render_unit_passes_the_session_bus():
    unit = service.render_unit("/usr/local/bin/linguapulse")
    assert "PassEnvironment=DBUS_SESSION_BUS_ADDRESS DISPLAY XAUTHORITY" in unit


def test_render_unit_restarts_after_a_failure():
    unit = service.render_unit("/usr/local/bin/linguapulse")
    assert "Restart=on-failure" in unit


def test_install_unit_writes_the_unit_file(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    path = service.install_unit("/usr/local/bin/linguapulse")
    assert path.exists()
    assert "linguapulse daemon" in path.read_text(encoding="utf-8")


def test_install_autostart_keeps_the_existing_content(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\nhc() { :; }\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    assert service.install_autostart() is True
    content = target.read_text(encoding="utf-8")
    assert "# my own settings" in content
    assert "hc() { :; }" in content
    assert service.AUTOSTART_BEGIN in content
    assert "systemctl --user start linguapulse.service" in content


def test_install_autostart_creates_a_backup(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    service.install_autostart()
    backup = tmp_path / "autostart.linguapulse.bak"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "# my own settings\n"


def test_install_autostart_is_idempotent(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    service.install_autostart()
    once = target.read_text(encoding="utf-8")
    assert service.install_autostart() is False
    assert target.read_text(encoding="utf-8") == once


def test_install_autostart_creates_the_file_when_it_is_missing(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    assert service.install_autostart() is True
    assert target.exists()


def test_remove_autostart_removes_only_the_block(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    service.install_autostart()
    assert service.remove_autostart() is True
    content = target.read_text(encoding="utf-8")
    assert "# my own settings" in content
    assert service.AUTOSTART_BEGIN not in content
    assert "linguapulse" not in content


def test_remove_autostart_without_a_block_does_nothing(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    assert service.remove_autostart() is False
    assert target.read_text(encoding="utf-8") == "# my own settings\n"


def test_install_reports_an_orphan_begin_marker(home, tmp_path, monkeypatch, capsys):
    target = tmp_path / "autostart"
    original = "# my own settings\n# >>> lingua-pulse >>>\nMod4-Shift-q = close\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert cli.main(["install", "--executable", "/usr/local/bin/linguapulse"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert str(target) in captured.err
    assert "malformed" in captured.err
    assert "left untouched" in captured.err
    assert target.read_text(encoding="utf-8") == original
    assert not service.unit_path().exists()


def test_uninstall_reports_an_orphan_begin_marker(home, tmp_path, monkeypatch, capsys):
    target = tmp_path / "autostart"
    original = (
        "# my own settings\n# >>> lingua-pulse >>>\n"
        "Mod4-Shift-q = close\nMod4-Return = spawn xterm\n"
    )
    target.write_text(original, encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert cli.main(["uninstall"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert str(target) in captured.err
    assert "malformed" in captured.err
    assert "left untouched" in captured.err
    assert target.read_text(encoding="utf-8") == original


def test_install_autostart_refuses_an_orphan_end_marker(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    original = "# my own settings\n# <<< lingua-pulse <<<\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    with pytest.raises(service.MalformedBlock):
        service.install_autostart()
    assert target.read_text(encoding="utf-8") == original


def test_remove_autostart_refuses_an_orphan_end_marker(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    original = "# my own settings\n# <<< lingua-pulse <<<\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    with pytest.raises(service.MalformedBlock):
        service.remove_autostart()
    assert target.read_text(encoding="utf-8") == original

```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_service.py -v`

Expected: FAIL with `ImportError: cannot import name 'service' from 'linguapulse'`.

- [ ] **Step 3: Write the implementation**

Create `src/linguapulse/service.py`:

```python
"""Installation of the systemd user unit and of the herbstluftwm autostart."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

UNIT_NAME = "linguapulse.service"
AUTOSTART_BEGIN = "# >>> lingua-pulse >>>"
AUTOSTART_END = "# <<< lingua-pulse <<<"
ENV_AUTOSTART = "LINGUAPULSE_AUTOSTART"

UNIT_TEMPLATE = """[Unit]
Description=lingua-pulse vocabulary scheduler
After=graphical-session.target

[Service]
Type=simple
ExecStart={executable} daemon
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
PassEnvironment=DBUS_SESSION_BUS_ADDRESS DISPLAY XAUTHORITY
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""

AUTOSTART_BLOCK = f"""{AUTOSTART_BEGIN}
# Start the lingua-pulse scheduler when the session starts.
systemctl --user start {UNIT_NAME}
{AUTOSTART_END}
"""


class MalformedBlock(ValueError):
    """Raised when only one of the two autostart markers is present."""


def unit_dir() -> Path:
    """Return the directory that holds the systemd user units."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "systemd" / "user"


def unit_path() -> Path:
    """Return the path of the systemd user unit."""
    return unit_dir() / UNIT_NAME


def autostart_path() -> Path:
    """Return the path of the herbstluftwm autostart file."""
    override = os.environ.get(ENV_AUTOSTART)
    if override:
        return Path(override)
    return Path.home() / ".config" / "herbstluftwm" / "autostart"


def default_executable() -> str:
    """Return the command that starts lingua-pulse."""
    found = shutil.which("linguapulse")
    if found:
        return found
    import sys

    return f"{sys.executable} -m linguapulse"


def render_unit(executable: str) -> str:
    """Return the content of the systemd user unit."""
    return UNIT_TEMPLATE.format(executable=executable)


def install_unit(executable: str) -> Path:
    """Write the systemd user unit."""
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_unit(executable), encoding="utf-8")
    return path


def remove_unit() -> bool:
    """Remove the systemd user unit."""
    path = unit_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def autostart_block() -> str:
    """Return the marked block that starts the scheduler."""
    return AUTOSTART_BLOCK


def check_autostart() -> None:
    """Raise MalformedBlock when only one of the two markers is present.

    A file with no marker, or with both markers, is left to the caller. A file
    with one marker but not the other is a hand edit or an interrupted write,
    and neither installing nor removing can tell where the block begins and
    ends, so the file is never touched.
    """
    path = autostart_path()
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if (AUTOSTART_BEGIN in content) != (AUTOSTART_END in content):
        raise MalformedBlock(
            f"{path}: the marked block is malformed, only one of its markers is present, "
            "the file was left untouched",
        )


def install_autostart() -> bool:
    """Add the marked block to the herbstluftwm autostart file.

    MalformedBlock is raised, and the file left untouched, when only one of the
    two markers is present.
    """
    check_autostart()
    path = autostart_path()
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    if AUTOSTART_BEGIN in original and AUTOSTART_END in original:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.stem + ".linguapulse.bak"))
    if original and not original.endswith("\n"):
        original += "\n"
    if original:
        original += "\n"
    path.write_text(original + autostart_block(), encoding="utf-8")
    return True


def remove_autostart() -> bool:
    """Remove the marked block from the herbstluftwm autostart file.

    MalformedBlock is raised, and the file left untouched, when only one of the
    two markers is present.
    """
    path = autostart_path()
    if not path.exists():
        return False
    check_autostart()
    original = path.read_text(encoding="utf-8")
    if AUTOSTART_BEGIN not in original:
        return False
    kept: list[str] = []
    inside = False
    for line in original.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == AUTOSTART_BEGIN:
            inside = True
            continue
        if stripped == AUTOSTART_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    path.write_text("".join(kept), encoding="utf-8")
    return True


def systemctl(*args: str) -> subprocess.CompletedProcess:
    """Run a systemctl user command."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def enable() -> bool:
    """Enable the user unit for the next login."""
    return systemctl("enable", UNIT_NAME).returncode == 0


def disable() -> bool:
    """Disable the user unit."""
    return systemctl("disable", UNIT_NAME).returncode == 0


def install(executable: str) -> list[str]:
    """Install the unit and the autostart, and report every step.

    MalformedBlock is raised, and nothing is written, when only one of the two
    autostart markers is present.
    """
    check_autostart()
    steps: list[str] = []
    unit = install_unit(executable)
    steps.append(f"wrote the user unit {unit}")
    if install_autostart():
        steps.append("added the herbstluftwm autostart block")
    else:
        steps.append("the herbstluftwm autostart block was already there")
    systemctl("daemon-reload")
    if enable():
        steps.append(f"enabled {UNIT_NAME} for the next login")
    else:
        steps.append(f"could not enable the unit, run: systemctl --user enable {UNIT_NAME}")
    return steps


def uninstall() -> list[str]:
    """Remove the unit and the autostart, and report every step.

    MalformedBlock is raised, and nothing is removed, when only one of the two
    autostart markers is present.
    """
    check_autostart()
    steps: list[str] = []
    if disable():
        steps.append(f"disabled {UNIT_NAME}")
    if remove_unit():
        steps.append(f"removed the user unit {unit_path()}")
    else:
        steps.append("there was no user unit to remove")
    if remove_autostart():
        steps.append("removed the herbstluftwm autostart block")
    else:
        steps.append("there was no herbstluftwm autostart block to remove")
    systemctl("daemon-reload")
    return steps
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_service.py -v`

Expected: PASS, 14 tests.

- [ ] **Step 5: Add the install and uninstall commands**

In `src/linguapulse/cli.py`, add `service` to the package imports, so that the line reads:

```python
from . import __version__, config, daemon, diagnostics, models, paths, review, service, srs, store, text
```

In `build_parser`, add:

```python
    install_parser = commands.add_parser("install", help="install the scheduler service")
    install_parser.add_argument("--executable", help="command that starts lingua-pulse")

    commands.add_parser("uninstall", help="remove the scheduler service")
```

Add the command implementations:

```python
def command_install(args: argparse.Namespace) -> int:
    """Install the systemd user unit and the herbstluftwm autostart."""
    executable = args.executable or service.default_executable()
    try:
        steps = service.install(executable)
    except service.MalformedBlock as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for step in steps:
        print(step)
    print("Log out and back in, or run: systemctl --user start linguapulse.service")
    return 0


def command_uninstall(args: argparse.Namespace) -> int:
    """Remove the systemd user unit and the herbstluftwm autostart."""
    try:
        steps = service.uninstall()
    except service.MalformedBlock as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for step in steps:
        print(step)
    return 0

```

Add the dispatch entries:

```python
        "install": command_install,
        "uninstall": command_uninstall,
```

- [ ] **Step 6: Run the whole test suite**

Run: `python3 -m pytest -v`

Expected: PASS, 246 tests, every test of every task.

- [ ] **Step 7: Commit (only when the user explicitly requested commits)**

```bash
git add src/linguapulse/cli.py src/linguapulse/service.py tests/test_service.py
git commit -m "feat: add the service installation and the autostart"
```

---

### Task 15: The Readme and the End to End Check

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the whole package.
- Produces: the user documentation of lingua-pulse.

- [ ] **Step 1: Write the README**

Create `README.md`:

```markdown
# lingua-pulse

A terminal first vocabulary trainer for Linux desktops. It keeps a small deck
of words in a plain JSON file, schedules every word with spaced repetition and
reminds you once, exactly when the word is due.

* No GUI, no tray icon, no web server, no background database.
* Standard library only, Python 3.11 or newer.
* One notification per due moment, never a pile of leftovers.

## Install

```bash
pipx install .
```

Or run it straight from the checkout:

```bash
PYTHONPATH=src python3 -m linguapulse --version
```

## Quick start

```bash
linguapulse seed                    # add a few example cards
linguapulse show --reveal           # look at the card that is due
linguapulse next good               # grade it
linguapulse status                  # what is due and when
linguapulse doctor                  # check that everything works
```

## Commands

| Command | What it does |
| --- | --- |
| `show` | Print the card that is due. `--reveal` shows the answer. |
| `next <grade>` | Grade the due card with `again`, `hard`, `good` or `easy`. |
| `history` | Show the recorded reviews. |
| `status` | Show the deck, the schedule and the service state. |
| `validate` | Check the deck file for problems. |
| `add` | Add a card. `--term`, `--lang` and `--text` are required. |
| `list` | List the cards of the deck. |
| `seed` | Add the bundled example cards. |
| `config` | Show or change the preferences. |
| `daemon` | Run the scheduler in the foreground. |
| `install` | Install the systemd user unit and the herbstluftwm autostart. |
| `uninstall` | Remove them again. |
| `doctor` | Check the installation. |

## How the scheduler works

The scheduler sleeps until the exact moment the next card is due. It does not
poll. When it wakes up it delivers one notification, remembers that the
occurrence was handled and computes the next wake up.

* Grading a card wakes the scheduler up right away, so the next card is
  scheduled without a delay.
* At most once per hour the scheduler rescans the files, that is the safety
  net for a deck that was edited by hand.
* A reminder that is more than 15 minutes late is skipped, not replayed.
* Older reminders of a backlog are dropped, only the newest one is delivered.
* A word that you grade with `again` comes back after 10 minutes, without a
  notification, so that you can relearn it in the terminal.

## How the notifications behave

* One notification per due moment, no retries.
* When the notification cannot be delivered, the problem is written to the service
  log (`journalctl --user -u linguapulse.service`) and the reason is actionable.

  If no notification appears, run `linguapulse doctor`: it prints the steps that
  diagnose the failure: a direct `notify-send` test, a `busctl` lookup of the
  notification daemon and the check that `DBUS_SESSION_BUS_ADDRESS` reaches the
  scheduler.
* Identical failures are logged once and then only every tenth time.

## Files

| Path | Content |
| --- | --- |
| `~/.local/share/linguapulse/deck.json` | The cards. |
| `~/.local/share/linguapulse/state.json` | The schedule of every card. |
| `~/.local/share/linguapulse/history.jsonl` | The recorded reviews. |
| `~/.config/linguapulse/config.json` | The preferences. |
| `~/.local/state/linguapulse/daemon.lock` | The lock that keeps one scheduler. |
| `~/.local/state/linguapulse/daemon.pid` | The process id of the scheduler. |

Set `LINGUAPULSE_HOME` to move the data, config and state directories under
one root, which is handy for tests.

## Installation of the service

```bash
linguapulse install
systemctl --user start linguapulse.service
```

`install` writes `~/.config/systemd/user/linguapulse.service`, enables it and
adds a marked block to `~/.config/herbstluftwm/autostart`. Your own autostart
file is never overwritten and a backup is written to
`autostart.linguapulse.bak`. Undo it with `linguapulse uninstall`, which removes
the marked block and the unit again.

## Development

```bash
python3 -m pytest -v
```

The tests run from the checkout, no installation is needed.
```

- [ ] **Step 2: Run the whole test suite**

Run: `python3 -m pytest -v`

Expected: PASS, 246 tests, every test of every task.

- [ ] **Step 3: Check the manual pages of the CLI**

Run: `PYTHONPATH=src python3 -m linguapulse --help` and `PYTHONPATH=src python3 -m linguapulse next --help`

Expected: the help text lists every command and every option.

- [ ] **Step 4: Run the CLI end to end in a scratch home**

```bash
export LINGUAPULSE_HOME="$(mktemp -d)"
PYTHONPATH=src python3 -m linguapulse seed
PYTHONPATH=src python3 -m linguapulse list
PYTHONPATH=src python3 -m linguapulse show --reveal
PYTHONPATH=src python3 -m linguapulse next good
PYTHONPATH=src python3 -m linguapulse history
PYTHONPATH=src python3 -m linguapulse status
PYTHONPATH=src python3 -m linguapulse validate
PYTHONPATH=src python3 -m linguapulse doctor
```

Expected: the seed adds the bundled cards, `show` prints the due card, `next
good` grades it and reports the next review, `history` lists the review,
`status` lists the remaining due cards (nine of the ten seeded, after one
grading), `validate` reports no problems and `doctor` reports the state of the
installation. The doctor exits with 1 when a check fails, which is the case
while the scheduler is not running yet.

- [ ] **Step 5: Check the install and uninstall round trip and the generated unit file in a scratch home**

```bash
export XDG_CONFIG_HOME="$(mktemp -d)"
export LINGUAPULSE_AUTOSTART="$(mktemp)"
PYTHONPATH=src python3 -m linguapulse install --executable /usr/bin/env
cat "$LINGUAPULSE_AUTOSTART"
systemd-analyze --user verify "$XDG_CONFIG_HOME/systemd/user/linguapulse.service"
PYTHONPATH=src python3 -m linguapulse uninstall
```

Expected: the install writes the unit and adds the marked block, the unit file
passes `systemd-analyze --user verify` (skip that line when `systemd-analyze` is
not installed), the uninstall removes both again and leaves the autostart file
otherwise unchanged.

- [ ] **Step 6: Commit (only when the user explicitly requested commits)**

```bash
git add README.md
git commit -m "docs: describe the usage of lingua-pulse"
```

---

## Appendix: What Each Task Delivers

| Spec area | Task |
| --- | --- |
| Package, version, console script | Task 1 |
| Unicode, bidirectional text, display width | Task 2 |
| XDG paths, atomic writes, history log | Task 3 |
| Cards, states, deck validation, local time zone | Task 4 |
| Spaced repetition grading | Task 5 |
| Preferences | Task 6 |
| Notification delivery | Task 7 |
| Reminder policy, grace window, backlog skipping | Task 8 |
| Card selection and terminal rendering | Task 9 |
| `show`, `next`, `history`, `status`, `validate` | Task 10 |
| `add`, `list`, `seed`, `config` | Task 11 |
| Scheduler, lock, wake up on demand | Task 12 |
| Diagnostics and `doctor` | Task 13 |
| systemd user unit, herbstluftwm autostart | Task 14 |
| Documentation and the end to end check | Task 15 |

## Appendix: The Failure Modes That Are Covered

| Failure mode | Where it is covered |
| --- | --- |
| A reminder arrives twice for the same occurrence | Task 8 `handled_due`, Task 12 `deliver_due` |
| A backlog of old reminders floods the desktop | Task 8 `plan_reminder`, Task 12 `deliver_due` |
| Two schedulers deliver the same reminder | Task 12 `acquire_lock` |
| A notification failure repeats in the log | Task 12 `FailureLog` |
| The scheduler wakes up too often | Task 12 `next_wakeup`, Task 13 `doctor` |
| A day interval shifts over a daylight saving change | Task 4 `add_wall_clock`, Task 5 `apply_grade` |
| Right to left text breaks the terminal output | Task 2 `isolate`, Task 9 `render_card` |
| The autostart file of the user is overwritten | Task 14 `install_autostart` |
