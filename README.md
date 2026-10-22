# lingua-pulse

A terminal first vocabulary trainer for Linux desktops. It keeps a small deck
of words in a plain JSON file, schedules every word with spaced repetition and
reminds you once, exactly when the word is due.

* No GUI, no tray icon, no web server, no background database.
* Standard library only, Python 3.11 or newer.
* One notification per due word, never a pile of leftovers.

## Install

```bash
pipx install .
```

Or run it straight from the checkout:

```bash
python3 -m linguapulse --version
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

* One notification per due card, no retries.
* When the notification cannot be delivered, the problem is written to the log
  of the service and the reason is actionable.
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

Set `LINGUAPULSE_HOME` to move every file into one directory, which is handy
for tests.

## Installation of the service

```bash
linguapulse install
systemctl --user start linguapulse.service
```

`install` writes `~/.config/systemd/user/linguapulse.service`, enables it and
adds a marked block to `~/.config/herbstluftwm/autostart`. Your own autostart
file is never overwritten and a backup is written to
`autostart.linguapulse.bak`.

## Development

```bash
python3 -m pytest -v
```

The tests run from the checkout, no installation is needed.
