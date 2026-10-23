# lingua-pulse

A terminal first vocabulary trainer for Linux desktops. It keeps a small deck
of words in a plain JSON file, schedules every word with spaced repetition and
reminds you when the word is due and keeps reminding you until you grade it.

* No GUI, no tray icon, no web server, no background database.
* Standard library only, Python 3.11 or newer.
* A due card reminds you every 10 minutes until you grade it.

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

`doctor` exits with 1 until the service is installed, so the `[FAIL] scheduler`
line is expected before `linguapulse install`.

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

When it wakes up it delivers one notification, records the reminder time and
computes the next wake up.

* Grading a card wakes the scheduler up right away, so the next card is
  scheduled without a delay.
* When nothing is scheduled, the scheduler rechecks the files at most once per
  hour. A deck that was edited by hand is picked up at that rescan, or when the
  scheduler next wakes for an already scheduled card.
* A due card that you do not grade reminds you again every 10 minutes, without
  a limit, until you grade it.
* After a restart, a missed reminder is delivered once and the 10-minute
  cadence resumes from there; missed slots are never replayed.
* A word that you grade with `again` comes back after 10 minutes, without a
  notification, so that you can relearn it in the terminal.

## How the notifications behave

* A due card notifies at its due time and then every 10 minutes until you grade it.
* When the notification cannot be delivered, the problem is written to the
  service log (`journalctl --user -u linguapulse.service`) and the reason is
  actionable.

  If no notification appears, run `linguapulse doctor`: it prints the steps that
  diagnose the failure: a direct `notify-send` test, a `busctl` lookup of the
  notification daemon and the check that `DBUS_SESSION_BUS_ADDRESS` reaches the
  scheduler.
* Identical failures are logged once and then only every tenth time, and the
  log reports when delivery recovers (`notifications are being delivered
  again`).
* `linguapulse config --no-notify` silences the desktop notifications; cards still come due, and no reminder wakeups are scheduled until notifications are enabled again.

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

## Terminal and fonts

* A UTF-8 locale is required, for example `LANG=en_US.UTF-8`; the Arabic and
  Chinese terms cannot be shown otherwise.
* Use a monospace font that covers Arabic and Simplified Chinese. Check the
  installed fonts with `fc-list :lang=ar` and `fc-list :lang=zh`.
* Chinese cards carry pinyin with tone marks, the font has to cover them too.
* Local scheduling needs the time zone database (`tzdata`). Without it the
  scheduler falls back to UTC.
* The supported language codes are `ar`, `en`, `es`, `fr`, `tr` and `zh`.

## Installation of the service

```bash
linguapulse install
systemctl --user start linguapulse.service
```

`install` writes `~/.config/systemd/user/linguapulse.service`, enables it and
adds a marked block to `~/.config/herbstluftwm/autostart`. Your own autostart
file is never overwritten and a backup is written to
`autostart.linguapulse.bak`. Undo it with `linguapulse uninstall`, which stops
the running service, disables the unit, and removes the unit and the marked
block again.

## Development

The tests need pytest, which the `dev` extra provides:

```bash
pip install -e '.[dev]'
python3 -m pytest -v
```

The tests run from the checkout against `src/`, no other installation is
needed.
