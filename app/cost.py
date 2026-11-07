"""Estimated spend from recorded model calls (Store.usage_since): python -m app cost --days 7."""

from __future__ import annotations

# USD per million tokens: (input, output, cache read). Anthropic first-party API rates as of 2026-10.
# Confirm at https://platform.claude.com/docs/en/about-claude/pricing before trusting a total.
# Haiku 5.5's cache-read rate isn't published in our source; 0.1x input is an estimate. Its prompts over
# 100K tokens cost more ($0.50 / $2.50); one deck's slides stay far below that.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
CACHE_WRITE = 1.25  # a 5-minute cache write costs 1.25x the input rate
ROW = "{step:<10} {model:<20} {calls:>6} {input_tokens:>10} {output_tokens:>9} {usd:>8}"


def usd(row: dict) -> float | None:
    """Estimated cost of one usage row, or None for a model with no known price."""
    price = PRICES.get(row["model"])
    if price is None:
        return None
    inp, out, cache_read = price
    total = (
        row["input_tokens"] * inp
        + row["output_tokens"] * out
        + row["cache_write_tokens"] * inp * CACHE_WRITE
        + row["cache_read_tokens"] * cache_read
    )
    return total / 1_000_000


def report(rows: list[dict], days: int) -> str:
    """A small table of calls, tokens and estimated USD per step and model, with a total."""
    if not rows:
        return f"No model calls recorded in the last {days} days."
    head = {
        "step": "step",
        "model": "model",
        "calls": "calls",
        "input_tokens": "input",
        "output_tokens": "output",
    }
    lines = [f"Model spend, last {days} days (estimated)", "", ROW.format(**head, usd="USD")]
    total, unknown = 0.0, []
    for r in rows:
        cost = usd(r)
        lines.append(ROW.format(**r, usd="?" if cost is None else f"{cost:.4f}"))
        if cost is None:
            unknown.append(r["model"])
        else:
            total += cost
    lines += ["", f"Total: ${total:.4f}"]
    if unknown:
        lines.append(f"No price for {', '.join(sorted(set(unknown)))}: add it to app/cost.py PRICES.")
    return "\n".join(lines)
