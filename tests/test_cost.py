import pytest

from app.__main__ import main
from app.cost import report, usd

ROW = {
    "step": "summarize",
    "model": "claude-sonnet-5-5",
    "calls": 2,
    "input_tokens": 1_000_000,
    "output_tokens": 100_000,
    "cache_write_tokens": 0,
    "cache_read_tokens": 1_000_000,
}


def test_usd_uses_input_output_and_cache_rates():
    assert usd(ROW) == pytest.approx(2.00 + 1.00 + 0.20)  # $2/M in, $10/M out, $0.20/M cache read
    assert usd({**ROW, "cache_read_tokens": 0, "cache_write_tokens": 1_000_000}) == pytest.approx(5.50)


def test_report_totals_known_models_and_flags_unknown_ones():
    text = report([ROW, {**ROW, "step": "judge", "model": "mystery"}], days=7)
    assert "Total: $3.2000" in text
    assert "No price for mystery" in text and "?" in text


def test_cost_command_reads_recorded_calls(store, capsys):
    store.record_call(
        "judge", "claude-haiku-5-5", {**{k: 0 for k in ROW if k.endswith("tokens")}, "input_tokens": 1000}
    )
    assert main(["cost", "--days", "3"], store=store) == 0
    out = capsys.readouterr().out
    assert "last 3 days" in out and "judge" in out and "claude-haiku-5-5" in out


def test_cost_command_with_nothing_recorded(store, capsys):
    assert main(["cost"], store=store) == 0
    assert "No model calls recorded in the last 7 days." in capsys.readouterr().out
