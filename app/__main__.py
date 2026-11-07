"""Command line: python -m app ingest <file> --course "CS 2" | python -m app ask "..." --course "CS 2"."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import httpx

from .config import ConfigError, settings, validate_settings
from .llm import make_llm
from .lms.canvas import CanvasClient, parse_ignore, parse_names
from .logs import setup_logging
from .pipeline import ask_course, ingest_file, sync_canvas
from .store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app", description="LazyGenius")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="parse, summarize, and verify a PDF or PPTX")
    ingest.add_argument("file", type=Path)
    ask = commands.add_parser("ask", help="ask a question about a course's slides")
    ask.add_argument("question")
    commands.add_parser("sync", help="pull new and changed lectures from Canvas")
    for command in (ingest, ask):
        command.add_argument("--course", required=True)
    for command in commands.choices.values():
        command.add_argument("--offline", action="store_true", help="no API key: quote slides, no AI")
    return parser


def _print_answer(answer: dict) -> None:
    if answer["insufficient_evidence"]:
        print("Not covered in the slides.")
    for claim in answer["claims"]:
        sources = ", ".join(f"{s['deck_title']} slide {s['slide']}" for s in claim["sources"])
        print(f"- {claim['text']} [{sources}]")


def main(argv: list[str] | None = None, llm=None, judge=None, store: Store | None = None, canvas=None) -> int:
    """Run the CLI and return its exit code. Tests inject `llm`, `judge`, and `store`."""
    args = _parser().parse_args(argv)
    cfg = replace(settings, offline=settings.offline or args.offline)
    setup_logging()
    try:
        validate_settings(cfg, need_model=llm is None)
        store = store or Store(cfg.db_path)
        if llm is None:
            llm, judge = make_llm(cfg, record=store.record_call)
        if args.command == "sync":
            if not canvas and not (cfg.canvas_base_url and cfg.canvas_token):
                raise ConfigError("Set CANVAS_BASE_URL and CANVAS_TOKEN to sync")
            canvas = canvas or CanvasClient(cfg.canvas_base_url, cfg.canvas_token)
            result = sync_canvas(
                canvas,
                store,
                llm,
                judge,
                cfg.files_dir,
                max_revisions=cfg.max_revisions,
                ignore=parse_ignore(cfg.canvas_ignore),
                names=parse_names(cfg.canvas_names),
            )
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "ingest":
            result = ingest_file(
                args.file,
                args.course,
                store,
                llm,
                judge,
                max_revisions=cfg.max_revisions,
                images_dir=cfg.images_dir,
            )
            print(json.dumps(result, indent=2))
            return 0
        answer = ask_course(args.course, args.question, store, llm, judge)
    except httpx.HTTPError as err:
        print(f"error: Canvas request failed ({type(err).__name__})", file=sys.stderr)
        return 2
    except (ConfigError, FileNotFoundError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if answer is None:
        print(f"error: no lectures for {args.course!r} yet", file=sys.stderr)
        return 1
    _print_answer(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
