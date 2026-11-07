"""Model access. The harness depends only on the `LLM` protocol, so tests can swap in a fake."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .config import settings
from .models import Answer, Claim, Deck, Issue, Slide, Summary
from .retrieval import tokenize

PROMPT_VERSION = "2"  # bump whenever SUMMARY_RULES, ANSWER_RULES, or the judge prompt change
# Output caps. Thinking is on by default for current models and counts toward max_tokens, so these leave room
# for it; a response that still hits the cap raises instead of being half-parsed.
WRITER_MAX_TOKENS = 16000
JUDGE_MAX_TOKENS = 2000
JUDGE_RULES = "Decide if EVIDENCE fully supports CLAIM. Give a one-sentence reason."


class LLMError(ValueError):
    """The model's reply can't be used: truncated, refused, or missing the requested result."""


class Verdict(BaseModel):
    supported: bool
    reason: str


class LLM(Protocol):
    model_id: str
    prompt_version: str

    def summarize(self, deck: Deck, feedback: list[Issue]) -> Summary: ...
    def answer(self, question: str, slides: list[tuple[str, Slide]], feedback: list[Issue]) -> Answer: ...


SUMMARY_RULES = """You summarize lecture slides for a student.
Rules:
- Every claim cites the slide numbers it comes from. Use only those slides.
- Copy numbers, formulas and technical terms exactly as written on the slide.
- Wrap code identifiers in backticks only if they appear on the slide.
- Prefer 4-8 claims.
- Add 1-3 visuals (concept_map, table, timeline, key_terms) only when the slides support them.
- If revising, fix or drop every claim listed under FEEDBACK."""

ANSWER_RULES = """Answer the student's question using ONLY the slides provided.
Every claim cites slides as numbers from the provided list. If the slides don't answer it,
set insufficient_evidence=true and return no claims. Never use outside knowledge."""


def _format_slides(slides: list[tuple[str, Slide]]) -> str:
    return "\n\n".join(f"[slide {s.number} | {deck}]\n{s.text}" for deck, s in slides if s.text)


def _format_feedback(feedback: list[Issue]) -> str:
    if not feedback:
        return ""
    lines = "\n".join(f"- {i.claim!r}: {i.detail}" for i in feedback)
    return f"\n\nFEEDBACK (previous attempt failed verification):\n{lines}"


def _check_stop(resp) -> None:
    if resp.stop_reason in ("max_tokens", "refusal"):
        raise LLMError(f"model stopped early: {resp.stop_reason}")


def _add_usage(totals: dict[str, int], resp) -> None:
    totals["input_tokens"] += resp.usage.input_tokens
    totals["output_tokens"] += resp.usage.output_tokens


class ClaudeLLM:
    """Uses forced tool calls so output is always valid JSON matching our pydantic models."""

    prompt_version = PROMPT_VERSION

    def __init__(self, model: str | None = None, client=None):
        import anthropic  # imported lazily so tests don't need a key

        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model_id = model or settings.model
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def _call(self, system: str, user: str, schema: dict, tool: str) -> dict:
        """One request that must end in a call to `tool`. Current models reject forced tool choice
        (tool_choice "tool"/"any" is a 400), so the prompt asks for the call and the reply is checked.
        The schema stays non-strict: strict mode would forbid the free-form `VisualSpec.data` object."""
        resp = self.client.messages.create(
            model=self.model_id,
            max_tokens=WRITER_MAX_TOKENS,
            system=f"{system}\nSubmit your result by calling the {tool} tool.",
            tools=[{"name": tool, "description": "Submit the result.", "input_schema": schema}],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": user}],
        )
        _add_usage(self.usage, resp)
        _check_stop(resp)
        call = next((b for b in resp.content if b.type == "tool_use" and b.name == tool), None)
        if call is None:
            raise LLMError(f"model did not call {tool}")
        return call.input

    def summarize(self, deck: Deck, feedback: list[Issue]) -> Summary:
        slides = _format_slides([(deck.title, s) for s in deck.slides])
        data = self._call(
            SUMMARY_RULES, slides + _format_feedback(feedback), Summary.model_json_schema(), "submit_summary"
        )
        return Summary.model_validate(data)

    def answer(self, question: str, slides: list[tuple[str, Slide]], feedback: list[Issue]) -> Answer:
        user = f"{_format_slides(slides)}\n\nQUESTION: {question}{_format_feedback(feedback)}"
        data = self._call(ANSWER_RULES, user, Answer.model_json_schema(), "submit_answer")
        return Answer.model_validate(data)


class ClaudeJudge:
    """LLM-as-judge for paraphrased claims. Use a cheaper model than the writer."""

    def __init__(self, model: str | None = None, client=None):
        import anthropic

        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model_id = model or settings.judge_model
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def supports(self, claim: str, evidence: str) -> tuple[bool, str]:
        """Structured output guarantees a JSON verdict even when the model thinks first. Fails closed:
        anything but a clean "supported" verdict rejects the claim."""
        try:
            resp = self.client.messages.parse(
                model=self.model_id,
                max_tokens=JUDGE_MAX_TOKENS,
                system=JUDGE_RULES,
                messages=[{"role": "user", "content": f"EVIDENCE:\n{evidence}\n\nCLAIM:\n{claim}"}],
                output_format=Verdict,
            )
        except ValueError:  # the reply wasn't a valid Verdict
            return False, "judge returned unparseable output"
        _add_usage(self.usage, resp)
        verdict = resp.parsed_output
        if resp.stop_reason != "end_turn" or verdict is None:
            return False, f"judge gave no verdict ({resp.stop_reason})"
        return verdict.supported, verdict.reason


class ExtractiveLLM:
    """Offline stand-in that quotes slides, for running the app with no API key. Not AI: it never
    paraphrases, so its output says nothing about how the real model or the verifier perform."""

    model_id = "extractive-offline"
    prompt_version = "none"

    def summarize(self, deck: Deck, feedback: list[Issue]) -> Summary:
        slides = [s for s in deck.slides if s.text][:8]
        return Summary(abstract=[Claim(text=_longest_line(s.text), slides=[s.number]) for s in slides])

    def answer(self, question: str, slides: list[tuple[str, Slide]], feedback: list[Issue]) -> Answer:
        wanted = set(tokenize(question))
        claims = []
        for _, slide in slides[:3]:
            matching = [ln for ln in slide.text.splitlines() if wanted & set(tokenize(ln))]
            if matching:
                claims.append(Claim(text=_longest_line("\n".join(matching)), slides=[slide.number]))
        return Answer(claims=claims, insufficient_evidence=not claims)


def _longest_line(text: str) -> str:
    return max(text.splitlines(), key=len)


def make_llm(cfg) -> tuple[LLM, object | None]:
    """The model and judge for these settings. Offline mode has no judge."""
    if cfg.offline:
        return ExtractiveLLM(), None
    return ClaudeLLM(), ClaudeJudge() if cfg.use_judge else None
