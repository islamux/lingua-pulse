"""Command line interface.

Every command is registered in one place, so each later task only adds one
entry to the parser and one entry to the dispatch table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from importlib import resources

from . import __version__, config, daemon, diagnostics, models, paths, review, service, srs, store, text


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
    loaded = load_deck_and_states()
    if loaded is None:
        return None
    cards, states = loaded
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

    commands.add_parser("daemon", help="run the scheduler in the foreground")
    commands.add_parser("doctor", help="check the installation")

    install_parser = commands.add_parser("install", help="install the scheduler service")
    install_parser.add_argument("--executable", help="command that starts lingua-pulse")

    commands.add_parser("uninstall", help="remove the scheduler service")

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
    print(f"Notify:     {'enabled' if settings.notify_enabled else 'disabled'}")
    print(f"Scheduler: {'running' if daemon.scheduler_is_running() else 'not running'}")
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
    if args.notify is not None:
        daemon.signal_scheduler()
    print(f"source_lang = {settings.source_lang}")
    print(f"target_lang = {settings.target_lang}")
    print(f"notify_enabled = {str(settings.notify_enabled).lower()}")
    return 0


def command_daemon(args: argparse.Namespace) -> int:
    """Run the scheduler in the foreground."""
    return daemon.run()


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
        "add": command_add,
        "list": command_list,
        "seed": command_seed,
        "config": command_config,
        "daemon": command_daemon,
        "doctor": command_doctor,
        "install": command_install,
        "uninstall": command_uninstall,
    }
    return handlers[args.command](args)
