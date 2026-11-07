"""Slide images, and the real Anthropic SDK against a mocked HTTP transport (no network, no cost)."""

import json
import shutil
from pathlib import Path

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app import api, parsing
from app.config import Settings
from app.llm import PROMPT_VERSION, ClaudeJudge, ClaudeLLM, LLMError, make_llm
from app.models import Issue
from app.parsing import render_images
from app.pipeline import ingest_file
from tests.conftest import GOOD_SUMMARY, FakeLLM


def test_pdf_renders_a_png_per_slide(pdf_file, tmp_path):
    assert render_images(pdf_file, tmp_path) == {1, 2, 3, 4}
    assert (tmp_path / "2.png").read_bytes().startswith(b"\x89PNG")


def test_pptx_without_libreoffice_falls_back_to_text(pptx_file, tmp_path, monkeypatch):
    monkeypatch.setattr(parsing.shutil, "which", lambda _: None)
    assert render_images(pptx_file, tmp_path) == set()


def test_pptx_with_libreoffice_converts_then_renders(pptx_file, pdf_file, tmp_path, monkeypatch):
    def fake_soffice(cmd, **_):
        shutil.copy(pdf_file, Path(cmd[cmd.index("--outdir") + 1]) / f"{pptx_file.stem}.pdf")

    monkeypatch.setattr(parsing.shutil, "which", lambda _: "soffice")
    monkeypatch.setattr(parsing.subprocess, "run", fake_soffice)
    assert render_images(pptx_file, tmp_path / "out") == {1, 2, 3, 4}


def test_render_failure_never_fails_ingest(pdf_file, store, tmp_path, monkeypatch):
    monkeypatch.setattr(parsing, "_render_pdf", lambda *_: 1 / 0)
    out = ingest_file(pdf_file, "C", store, FakeLLM(summaries=[GOOD_SUMMARY]), None, images_dir=tmp_path)
    assert not store.get_deck(out["deck_id"]).slide(1).has_image


def test_image_endpoint(pdf_file, store, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "settings", Settings(data_dir=tmp_path))
    client = TestClient(api.create_app(store, FakeLLM(summaries=[GOOD_SUMMARY])))
    with pdf_file.open("rb") as fh:
        deck_id = client.post("/upload", data={"course": "C"}, files={"file": ("l.pdf", fh)}).json()[
            "deck_id"
        ]
    r = client.get(f"/decks/{deck_id}/slides/2/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get(f"/decks/{deck_id}/slides/99/image").status_code == 404
    assert client.get("/decks/nope/slides/1/image").status_code == 404


def test_summary_records_model_and_prompt_version(pdf_file, store):
    out = ingest_file(pdf_file, "C", store, FakeLLM(summaries=[GOOD_SUMMARY]), None)
    saved = store.get_summary(out["deck_id"])
    assert saved["model"] == "fake" and saved["prompt_version"] == "test"


def _sdk(reply: dict, seen: list) -> anthropic.Anthropic:
    base = {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": "x",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json={**base, **reply})

    return anthropic.Anthropic(
        api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )


def _tool_reply(data: dict, name: str = "submit_summary", stop: str = "tool_use") -> dict:
    thinking = {"type": "thinking", "thinking": "", "signature": "s"}  # current models think first
    return {
        "stop_reason": stop,
        "content": [thinking, {"type": "tool_use", "id": "t", "name": name, "input": data}],
    }


def test_summarize_asks_for_the_tool_and_sends_feedback(sorting_deck):
    seen = []
    client = _sdk(_tool_reply({"abstract": [{"text": "A claim.", "slides": [2]}]}), seen)
    llm = ClaudeLLM(model="writer", client=client)
    feedback = [Issue(claim="old", check="exact_fact", detail="wrong")]
    summary = llm.summarize(sorting_deck, feedback)
    assert summary.abstract[0].slides == [2]
    # forced tool choice ("tool"/"any") is a 400 on current models: ask for the call instead
    assert seen[0]["model"] == "writer" and seen[0]["tool_choice"] == {"type": "auto"}
    assert "calling the submit_summary tool" in seen[0]["system"]
    assert (
        "FEEDBACK" in seen[0]["messages"][0]["content"] and "[slide 2 |" in seen[0]["messages"][0]["content"]
    )
    assert llm.usage == {"input_tokens": 10, "output_tokens": 5} and llm.prompt_version == PROMPT_VERSION


def test_answer_parses_tool_output_and_uses_the_ask_model():
    seen = []
    client = _sdk(_tool_reply({"claims": [], "insufficient_evidence": True}, "submit_answer"), seen)
    assert ClaudeLLM("writer", "asker", client=client).answer("q", [], []).insufficient_evidence
    assert seen[0]["model"] == "asker"


@pytest.mark.parametrize(
    "reply, error",
    [
        ({"content": [{"type": "text", "text": "Here is my summary..."}]}, "did not call submit_summary"),
        (_tool_reply({"abstract": []}, stop="max_tokens"), "max_tokens"),
        ({"stop_reason": "refusal", "content": []}, "refusal"),
    ],
)
def test_unusable_writer_replies_raise(sorting_deck, reply, error):
    with pytest.raises(LLMError, match=error):
        ClaudeLLM(client=_sdk(reply, [])).summarize(sorting_deck, [])


@pytest.mark.parametrize(
    "text, stop, expected",
    [
        ('{"supported": true, "reason": "ok"}', "end_turn", True),
        ('{"supported": false, "reason": "no"}', "end_turn", False),
        ('{"supported": true}', "end_turn", False),  # missing reason: not a valid verdict
        ("not json", "end_turn", False),
        ('{"supported": true, "reason": "ok"}', "max_tokens", False),
    ],
)
def test_judge_fails_closed_on_bad_output(text, stop, expected):
    thinking = {"type": "thinking", "thinking": "", "signature": "s"}  # first block isn't the verdict
    reply = {"stop_reason": stop, "content": [thinking, {"type": "text", "text": text}]}
    seen = []
    assert ClaudeJudge(client=_sdk(reply, seen)).supports("claim", "evidence")[0] is expected
    assert seen[0]["output_config"]["format"]["type"] == "json_schema"


def test_make_llm_offline_has_no_judge(tmp_path):
    llm, judge = make_llm(Settings(offline=True, data_dir=tmp_path))
    assert llm.model_id == "extractive-offline" and judge is None


def test_make_llm_routes_one_model_per_step(tmp_path):
    cfg = Settings(
        anthropic_api_key="test", model_writer="w", model_ask="a", model_judge="j", data_dir=tmp_path
    )
    llm, judge = make_llm(cfg)
    assert (llm.model_id, llm.ask_model, judge.model_id) == ("w", "a", "j")


def test_old_model_variables_still_work(monkeypatch):
    import importlib

    import app.config as config

    monkeypatch.setenv("HARNESS_MODEL", "old-writer")
    monkeypatch.delenv("MODEL_WRITER", raising=False)
    monkeypatch.setenv("MODEL_JUDGE", "new-judge")
    monkeypatch.setenv("HARNESS_JUDGE_MODEL", "old-judge")
    try:
        cfg = importlib.reload(config).Settings()
        assert cfg.model_writer == "old-writer" and cfg.model_judge == "new-judge"  # new name wins
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_every_call_is_recorded_even_when_the_reply_is_unusable(sorting_deck):
    calls = []
    reply = _tool_reply({"abstract": []}, stop="max_tokens")
    reply["usage"] = {"input_tokens": 900, "output_tokens": 16000, "cache_read_input_tokens": 100}
    llm = ClaudeLLM("writer", client=_sdk(reply, []), record=lambda *call: calls.append(call))
    with pytest.raises(LLMError):
        llm.summarize(sorting_deck, [])
    used = {"input_tokens": 900, "output_tokens": 16000, "cache_write_tokens": 0, "cache_read_tokens": 100}
    assert calls == [("summarize", "writer", used)]

    judge_reply = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": '{"supported": true, "reason": "ok"}'}],
    }
    ClaudeJudge("j", client=_sdk(judge_reply, []), record=lambda *call: calls.append(call)).supports("c", "e")
    assert calls[-1][:2] == ("judge", "j")
