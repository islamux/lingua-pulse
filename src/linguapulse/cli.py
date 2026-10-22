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
    states[card.id] = updated
    models.save_states(paths.state_path(), states)
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
