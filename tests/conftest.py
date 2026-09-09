from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _event(kind: str, blocks: list[dict], **extra: object) -> dict:
    return {"type": kind, "message": {"content": blocks}, **extra}


def user_text(text: str, *, meta: bool = False) -> dict:
    return _event("user", [{"type": "text", "text": text}], isMeta=meta)


def assistant_text(text: str) -> dict:
    return _event("assistant", [{"type": "text", "text": text}])


def tool_use(name: str, **inputs: object) -> dict:
    return _event(
        "assistant",
        [{"type": "tool_use", "name": name, "input": dict(inputs)}],
    )


@pytest.fixture
def make_session():
    """Write a synthetic .jsonl session and return its path."""

    def _make(directory: Path, name: str, events: list[dict], mtime: float | None = None) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.jsonl"
        path.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    return _make
