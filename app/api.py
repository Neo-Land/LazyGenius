"""HTTP API the Next.js frontend talks to.  Run: uvicorn app.api:app --reload"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import settings, validate_settings
from .lms.canvas import CanvasClient, parse_ignore, parse_names
from .models import Deck, Slide, Summary, VerificationReport
from .parsing import SUPPORTED
from .pipeline import ask_course, ingest_file, sync_canvas
from .store import Store


class AskRequest(BaseModel):
    course: str
    question: str = Field(min_length=1, max_length=500)


class AskLimiter:
    """Limits questions per visitor per minute and overall per day, so a public demo can't overspend.

    ponytail: in-memory, so limits reset on restart and need one server. Move to shared storage to scale."""

    def __init__(self, per_minute: int, per_day: int, clock: Callable[[], float] = time.time):
        self.per_minute, self.per_day, self.clock = per_minute, per_day, clock
        self.recent: dict[str, list[float]] = {}
        self.day, self.today = -1, 0

    def allow(self, visitor: str) -> bool:
        """Count this question if it is within both limits."""
        now = self.clock()
        if int(now // 86400) != self.day:
            self.day, self.today, self.recent = int(now // 86400), 0, {}
        recent = [t for t in self.recent.get(visitor, []) if now - t < 60]
        if self.today >= self.per_day or len(recent) >= self.per_minute:
            return False
        self.recent[visitor] = [*recent, now]
        self.today += 1
        return True


class CourseOut(BaseModel):
    course: str
    decks: int
    last_synced: str | None = None


class AppConfig(BaseModel):
    canvas: bool
    demo: bool


class DeckListItem(BaseModel):
    id: str
    title: str
    slides: int


class DeckDetail(BaseModel):
    deck: Deck
    summary: Summary | None = None
    report: VerificationReport | None = None
    attempts: int | None = None
    model: str | None = None
    prompt_version: str | None = None


class IngestResult(BaseModel):
    deck_id: str
    title: str
    attempts: int
    supported: int
    total: int
    needs_ocr: list[int]


class Source(BaseModel):
    deck_id: str
    deck_title: str
    slide: int


class AnswerClaim(BaseModel):
    text: str
    sources: list[Source]


class AskResponse(BaseModel):
    insufficient_evidence: bool
    claims: list[AnswerClaim]
    report: VerificationReport


def create_app(store: Store, llm, judge=None, canvas=None) -> FastAPI:
    app = FastAPI(title="LazyGenius")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    limiter = AskLimiter(settings.demo_asks_per_minute, settings.demo_asks_per_day)

    def refuse_in_demo() -> None:
        if settings.demo:
            raise HTTPException(403, "This demo is read-only.")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/config", response_model=AppConfig)
    def config():
        return {"canvas": canvas is not None and not settings.demo, "demo": settings.demo}

    @app.get("/courses", response_model=list[CourseOut])
    def courses():
        return store.courses()

    @app.get("/courses/{course:path}/decks", response_model=list[DeckListItem])
    def decks(course: str):
        return [
            {"id": d.id, "title": d.title, "slides": len(d.slides)} for d in store.decks_for_course(course)
        ]

    @app.get("/decks/{deck_id}", response_model=DeckDetail)
    def deck(deck_id: str):
        d = store.get_deck(deck_id)
        if not d:
            raise HTTPException(404, "deck not found")
        return {"deck": d.model_dump(), **(store.get_summary(deck_id) or {})}

    @app.get("/decks/{deck_id}/slides/{n}", response_model=Slide)
    def slide(deck_id: str, n: int):
        d = store.get_deck(deck_id)
        s = d.slide(n) if d else None
        if not s:
            raise HTTPException(404, "slide not found")
        return s.model_dump()

    @app.get("/decks/{deck_id}/slides/{n}/image")
    def slide_image(deck_id: str, n: int):
        d = store.get_deck(deck_id)  # an id from the database, so never a path from the request
        s = d.slide(n) if d else None
        if not s or not s.has_image:
            raise HTTPException(404, "no image for that slide")
        return FileResponse(settings.images_dir / d.id / f"{n}.png", media_type="image/png")

    @app.post("/upload", response_model=IngestResult)
    def upload(course: str = Form(...), file: UploadFile = File(...)):
        """Manual upload: lets you use the app without Canvas access."""
        refuse_in_demo()
        ext = Path(file.filename or "").suffix.lower()
        if ext not in SUPPORTED:
            raise HTTPException(400, f"only {sorted(SUPPORTED)} supported")
        dest = settings.files_dir / "uploads" / Path(file.filename).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        try:
            return ingest_file(
                dest,
                course,
                store,
                llm,
                judge,
                max_revisions=settings.max_revisions,
                images_dir=settings.images_dir,
            )
        except ValueError as err:
            raise HTTPException(400, str(err)) from err

    @app.post("/sync", response_model=list[IngestResult])
    def sync():
        refuse_in_demo()
        if canvas is None:
            raise HTTPException(400, "Canvas not configured (set CANVAS_BASE_URL and CANVAS_TOKEN)")
        try:
            return sync_canvas(
                canvas,
                store,
                llm,
                judge,
                settings.files_dir,
                max_revisions=settings.max_revisions,
                ignore=parse_ignore(settings.canvas_ignore),
                names=parse_names(settings.canvas_names),
            )
        except httpx.HTTPStatusError as err:
            if err.response.status_code in (401, 403):
                raise HTTPException(502, "Canvas rejected the token. Create a new one in Canvas.") from err
            raise HTTPException(502, f"Canvas returned status {err.response.status_code}.") from err
        except httpx.TransportError as err:
            raise HTTPException(502, "Can't reach Canvas. Check CANVAS_BASE_URL.") from err

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest, request: Request):
        visitor = request.client.host if request.client else "unknown"
        if settings.demo and not limiter.allow(visitor):
            raise HTTPException(429, "The demo's question limit was reached. Try again later.")
        answer = ask_course(req.course, req.question, store, llm, judge)
        if answer is None:
            raise HTTPException(404, "no lectures for that course yet")
        return answer

    return app


def _default_app() -> FastAPI:
    from .llm import make_llm
    from .logs import setup_logging

    setup_logging()
    validate_settings(settings)
    canvas = None
    if settings.canvas_base_url and settings.canvas_token:
        canvas = CanvasClient(settings.canvas_base_url, settings.canvas_token)
    store = Store(settings.db_path)
    llm, judge = make_llm(settings, record=store.record_call)
    return create_app(store, llm, judge, canvas)


def __getattr__(name):  # lazy so importing app.api in tests doesn't need an API key
    if name == "app":
        return _default_app()
    raise AttributeError(name)
