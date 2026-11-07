from app.models import VerificationReport
from app.store import Store
from tests.conftest import GOOD_SUMMARY


def test_deck_round_trip(store, sorting_deck):
    store.save_deck(sorting_deck)
    assert store.get_deck("d1") == sorting_deck
    assert store.get_deck("missing") is None


def test_is_current_tracks_source_version(store, sorting_deck):
    assert not store.is_current("d1", "v1")
    store.save_deck(sorting_deck, "v1")
    assert store.is_current("d1", "v1") and not store.is_current("d1", "v2")


def test_courses_and_decks_by_course(store, sorting_deck):
    store.save_deck(sorting_deck)
    store.save_deck(sorting_deck.model_copy(update={"id": "d2"}))
    store.save_deck(sorting_deck.model_copy(update={"id": "d3", "course": "Bio"}))
    assert store.courses() == [
        {"course": "Bio", "decks": 1, "last_synced": None},
        {"course": "CS 2", "decks": 2, "last_synced": None},
    ]
    assert {d.id for d in store.decks_for_course("CS 2")} == {"d1", "d2"}


def test_summary_round_trip_and_overwrite(store, sorting_deck):
    store.save_deck(sorting_deck)
    assert store.get_summary("d1") is None
    store.save_summary("d1", GOOD_SUMMARY, VerificationReport(passed=False), 3)
    store.save_summary("d1", GOOD_SUMMARY, VerificationReport(passed=True), 1)
    saved = store.get_summary("d1")
    assert saved["attempts"] == 1 and saved["report"]["passed"]
    assert len(saved["summary"]["abstract"]) == 3


def test_traces_keep_every_attempt_in_order(store):
    store.save_trace("summary", "d1", [{"attempt": 1}, {"attempt": 2}])
    store.save_trace("ask", "CS 2", [{"attempt": 1}])
    assert [t["attempt"] for t in store.get_traces("d1")] == [1, 2]


def test_data_survives_reopening(tmp_path, sorting_deck):
    path = tmp_path / "sub" / "h.db"
    Store(path).save_deck(sorting_deck)
    assert Store(path).get_deck("d1") == sorting_deck


def test_records_calls_and_sums_usage_per_step_and_model(store):
    used = {"input_tokens": 100, "output_tokens": 20, "cache_write_tokens": 0, "cache_read_tokens": 50}
    store.record_call("judge", "claude-haiku-5-5", used)
    store.record_call("judge", "claude-haiku-5-5", used)
    store.record_call("summarize", "claude-sonnet-5-5", used)
    rows = store.usage_since(days=7)
    assert [(r["step"], r["calls"], r["input_tokens"], r["cache_read_tokens"]) for r in rows] == [
        ("judge", 2, 200, 100),
        ("summarize", 1, 100, 50),
    ]
    store.db.execute("UPDATE calls SET created_at = datetime('now', '-10 days') WHERE step = 'summarize'")
    assert [r["step"] for r in store.usage_since(days=7)] == ["judge"]
