"""Measure the harness. Offline by default: python -m evals.run
Live, which costs money (run by Neo): python -m evals.run --live --max-usd 1"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path

from app.config import settings, validate_settings
from app.facts import norm
from app.harness import summarize_deck
from app.llm import ExtractiveLLM, make_llm
from app.models import Claim, Deck, Summary
from app.parsing import parse_file
from app.verifier import check_claim

from .decks import DECKS_DIR, fetch_decks

ROOT = Path(__file__).parent
# USD per million tokens (input, output). Deliberately on the high side so the budget stop trips early.
# ponytail: hand-kept prices; confirm at https://platform.claude.com/docs/en/about-claude/pricing
PRICES = {"writer": (4.0, 20.0), "judge": (1.0, 5.0)}


def captured(point: dict, claims: list[Claim]) -> bool:
    """A golden point counts if one claim citing one of its slides contains all of its keywords."""
    return any(
        set(c.slides) & set(point["slides"]) and all(k in norm(c.text) for k in point["keywords"])
        for c in claims
    )


def score_deck(deck: Deck, golden: dict, result) -> dict:
    """Grounding, coverage, and revisions for one summarized deck."""
    first = result.trace[0]["report"] if result.trace else {"claims_supported": 0, "claims_total": 0}
    summary: Summary = result.output
    hits = [captured(p, summary.abstract) for p in golden["point"]]
    return {
        "deck": deck.id,
        "first_attempt_supported": first["claims_supported"],
        "first_attempt_total": first["claims_total"],
        "final_claims": len(summary.abstract),
        "golden_points": len(hits),
        "golden_captured": sum(hits),
        "revisions": max(result.attempts - 1, 0),
        "golden_reviewed": golden["reviewed"],
    }


def score_planted(planted: dict, decks: dict[str, Deck], judge=None) -> dict:
    """How many planted errors the verifier catches, by kind, and how many true claims it rejects."""
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    missed = []
    for item in planted["claim"]:
        claim = Claim(text=item["text"], slides=item["slides"])
        flagged = bool(check_claim(claim, decks[item["deck"]], judge))
        by_kind[item["kind"]][0] += flagged
        by_kind[item["kind"]][1] += 1
        if flagged != item["expect_fail"]:
            missed.append({"kind": item["kind"], "deck": item["deck"], "text": item["text"]})
    errors = [v for k, v in by_kind.items() if k != "control"]
    control = by_kind.get("control", [0, 0])
    return {
        "recall": sum(v[0] for v in errors) / max(sum(v[1] for v in errors), 1),
        "errors_caught": sum(v[0] for v in errors),
        "errors_total": sum(v[1] for v in errors),
        "false_alarms": control[0],
        "controls_total": control[1],
        "by_kind": {k: {"flagged": v[0], "total": v[1]} for k, v in by_kind.items()},
        "wrong_verdicts": missed,
        "reviewed": planted["reviewed"],
    }


def spent(llm, judge) -> float:
    """Estimated USD so far from token counts. Zero for offline models."""
    total = 0.0
    for client, role in ((llm, "writer"), (judge, "judge")):
        usage = getattr(client, "usage", None)
        if usage:
            input_price, output_price = PRICES[role]
            total += (usage["input_tokens"] * input_price + usage["output_tokens"] * output_price) / 1e6
    return total


def run(
    decks: dict[str, Deck], goldens: dict, planted: dict, llm, judge, max_usd: float, revisions: int
) -> dict:
    """Score every deck, stopping when the budget is reached. Planted claims run first: they only
    use the judge, so a stop still leaves verifier numbers."""
    report = {"model": llm.model_id, "planted": score_planted(planted, decks, judge), "decks": []}
    report["stopped_early"] = False
    for name, deck in decks.items():
        if spent(llm, judge) >= max_usd:
            report["stopped_early"] = True
            break
        before = spent(llm, judge)
        result = summarize_deck(deck, llm, judge, revisions)
        report["decks"].append({**score_deck(deck, goldens[name], result), "usd": spent(llm, judge) - before})
    done = report["decks"]
    report["totals"] = {
        "grounding_first_attempt": sum(d["first_attempt_supported"] for d in done)
        / max(sum(d["first_attempt_total"] for d in done), 1),
        "coverage": sum(d["golden_captured"] for d in done) / max(sum(d["golden_points"] for d in done), 1),
        "revisions_per_deck": sum(d["revisions"] for d in done) / max(len(done), 1),
        "usd_total": spent(llm, judge),
    }
    return report


def load(decks_dir: Path = DECKS_DIR, root: Path = ROOT) -> tuple[dict, dict, dict]:
    """Parse the decks and read the golden and planted sets."""
    goldens = {p.stem: tomllib.loads(p.read_text()) for p in sorted((root / "golden").glob("*.toml"))}
    decks = {name: parse_file(decks_dir / f"{name}.pdf", "evals", name) for name in goldens}
    return decks, goldens, tomllib.loads((root / "planted.toml").read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use the real model. COSTS MONEY")
    parser.add_argument("--max-usd", type=float, default=1.0, help="stop starting decks at this estimate")
    args = parser.parse_args()
    if args.live:
        cfg = replace(settings, offline=False)
        validate_settings(cfg)
        llm, judge = make_llm(cfg)
    else:
        llm, judge = ExtractiveLLM(), None

    fetch_decks()
    report = run(*load(), llm, judge, args.max_usd, settings.max_revisions)
    report["date"] = date.today().isoformat()
    report["mode"] = "live" if args.live else "offline"
    out = ROOT / "reports" / f"{report['mode']}-{report['date']}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("model", "totals", "planted", "stopped_early")}, indent=2))
    print(f"Full report: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
