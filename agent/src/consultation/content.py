"""定型の文言、フォームの JSON Schema、やり取りの上限 (`agent/content/`) の読み込み。"""

import json
import os
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

CONTENT_DIR_ENV = "CONSULTATION_CONTENT_DIR"
DEFAULT_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"


@dataclass(frozen=True)
class Content:
    max_turns: int
    greeting: str
    profile_form: str
    first_message: str
    turn_limit: str
    feedback_form: str
    thanks: str
    content_filtered: str
    profile_schema: dict[str, Any]
    feedback_schema: dict[str, Any]


def content_dir() -> Path:
    return Path(os.environ.get(CONTENT_DIR_ENV) or DEFAULT_CONTENT_DIR)


@cache
def load(directory: Path | None = None) -> Content:
    directory = directory or content_dir()
    messages = tomllib.loads((directory / "messages.toml").read_text(encoding="utf-8"))
    texts = {k: v.strip() for k, v in messages.items() if isinstance(v, str)}
    return Content(
        max_turns=int(messages["max_turns"]),
        **texts,
        profile_schema=_json(directory / "profile.schema.json"),
        feedback_schema=_json(directory / "feedback.schema.json"),
    )


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
