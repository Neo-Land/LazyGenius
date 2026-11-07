"""Settings from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Configuration is unusable. Messages name settings, never their values."""


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number") from None


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    # One model per step (docs/BUILD_PLAN.md, Model routing). HARNESS_MODEL / HARNESS_JUDGE_MODEL still work.
    model_writer: str = os.getenv("MODEL_WRITER") or os.getenv("HARNESS_MODEL", "claude-sonnet-5-5")
    model_ask: str = os.getenv("MODEL_ASK", "claude-haiku-5-5")
    model_judge: str = os.getenv("MODEL_JUDGE") or os.getenv("HARNESS_JUDGE_MODEL", "claude-haiku-5-5")
    max_revisions: int = _int_env("HARNESS_MAX_REVISIONS", 2)
    use_judge: bool = os.getenv("HARNESS_USE_JUDGE", "true").lower() == "true"

    offline: bool = os.getenv("HARNESS_OFFLINE", "false").lower() == "true"  # no API key, no AI

    demo: bool = os.getenv("HARNESS_DEMO", "false").lower() == "true"  # read-only public demo
    demo_asks_per_minute: int = _int_env("HARNESS_DEMO_ASKS_PER_MINUTE", 5)  # per visitor
    demo_asks_per_day: int = _int_env("HARNESS_DEMO_ASKS_PER_DAY", 100)  # everyone, this caps spend
    cors_origins: str = os.getenv("HARNESS_CORS_ORIGINS", "http://localhost:3000")

    canvas_base_url: str | None = os.getenv("CANVAS_BASE_URL")  # e.g. https://<school>.instructure.com
    canvas_token: str | None = os.getenv("CANVAS_TOKEN")
    canvas_ignore: str = os.getenv("CANVAS_IGNORE_COURSES", "")  # Advising;Library
    canvas_names: str = os.getenv("CANVAS_COURSE_NAMES", "")  # CMPT-270-01=Algorithms;MATH-122=Calculus

    data_dir: Path = Path(os.getenv("HARNESS_DATA_DIR", "data"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "harness.db"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


settings = Settings()


def validate_settings(cfg: Settings, need_model: bool = True) -> None:
    """Raise ConfigError listing every problem, so a bad setup fails at startup with a clear message."""
    problems = []
    if need_model and not cfg.offline and not cfg.anthropic_api_key:
        problems.append("ANTHROPIC_API_KEY is not set (or use offline mode: HARNESS_OFFLINE=true)")
    if cfg.max_revisions < 0:
        problems.append("HARNESS_MAX_REVISIONS must be 0 or more")
    if bool(cfg.canvas_base_url) != bool(cfg.canvas_token):
        problems.append("CANVAS_BASE_URL and CANVAS_TOKEN must be set together")
    try:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(cfg.data_dir, os.W_OK):
            problems.append(f"HARNESS_DATA_DIR is not writable: {cfg.data_dir}")
    except OSError:
        problems.append(f"HARNESS_DATA_DIR cannot be created: {cfg.data_dir}")
    if problems:
        raise ConfigError("Invalid configuration:\n- " + "\n- ".join(problems))
