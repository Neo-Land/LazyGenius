"""Run one deck through the real model and print the verification report. COSTS MONEY.

Usage: python scripts/smoke_live.py deck.pdf --course "Demo"
Only for openly licensed decks if the output will be shared. Stores nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import cost  # noqa: E402
from app.config import ConfigError, settings, validate_settings  # noqa: E402
from app.harness import summarize_deck  # noqa: E402
from app.llm import make_llm  # noqa: E402
from app.parsing import parse_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--course", default="Smoke test")
    args = parser.parse_args()
    cfg = replace(settings, offline=False)
    try:
        validate_settings(cfg)
        deck = parse_file(args.file, args.course)
    except (ConfigError, FileNotFoundError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    calls = []
    llm, judge = make_llm(
        cfg, record=lambda step, model, used: calls.append({"step": step, "model": model, **used})
    )
    result = summarize_deck(deck, llm, judge, cfg.max_revisions)
    usage = {"writer": llm.usage, "judge": judge.usage if judge else None}
    priced = [cost.usd(c) for c in calls]
    run = {
        "model": llm.model_id,
        "judge_model": judge.model_id if judge else None,
        "calls": len(calls),
        "usd_estimate": None if None in priced else round(sum(priced), 4),
        "prompt_version": llm.prompt_version,
        "attempts": result.attempts,
        "report": result.report.model_dump(),
        "tokens": usage,
    }
    print(json.dumps(run, indent=2))
    for claim in result.output.abstract:
        print(f"- {claim.text} {claim.slides}")
    return 0 if result.output.abstract else 1


if __name__ == "__main__":
    sys.exit(main())
