from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CHUNK_LIMIT = 350_000
SESSION_MARKER = "\n\n##### SESSION "
_MAX_TEXT = 6000
_MAX_TOOL = 200


def _blocks(message: object) -> list[dict]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block for block in (content or []) if isinstance(block, dict)]


def _tool_summary(block: dict) -> str:
    payload = block.get("input") or {}
    for key in ("command", "file_path", "prompt", "skill", "pattern"):
        value = payload.get(key)
        if value:
            return str(value)[:_MAX_TOOL]
    return ""


def condense_session(path: Path) -> str:
    """Reduce one session to readable text: who said what, and what ran.

    Tool results are dropped: they are bulky, and what matters for a digest
    is the intent and the outcome, which the surrounding text carries.
    """
    lines = [f"{SESSION_MARKER.strip()} {path.stem}"]

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        kind = event.get("type")
        if kind not in {"user", "assistant"}:
            continue
        if kind == "user" and event.get("isMeta"):
            continue

        speaker = "USER" if kind == "user" else "CLAUDE"
        for block in _blocks(event.get("message")):
            block_type = block.get("type")
            if block_type == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    lines.append(f"[{speaker}] {text[:_MAX_TEXT]}")
            elif block_type == "tool_use":
                lines.append(f"[TOOL {block.get('name', '?')}] {_tool_summary(block)}")

    return "\n".join(lines)


def chunk(text: str, limit: int) -> list[str]:
    """Split text into pieces no larger than limit, preferring session breaks.

    Concatenating the result reproduces the input exactly; nothing is lost
    at a boundary.
    """
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []
    for index, part in enumerate(text.split(SESSION_MARKER)):
        restored = part if index == 0 else SESSION_MARKER + part
        while len(restored) > limit:
            pieces.append(restored[:limit])
            restored = restored[limit:]
        if restored:
            pieces.append(restored)

    merged: list[str] = []
    for piece in pieces:
        if merged and len(merged[-1]) + len(piece) <= limit:
            merged[-1] += piece
        else:
            merged.append(piece)
    return merged


def extract_project(
    paths: list[Path], limit: int = DEFAULT_CHUNK_LIMIT
) -> list[str]:
    """Condense every session of a project, oldest first, then chunk."""
    ordered = sorted(paths, key=lambda p: p.stat().st_mtime)
    return chunk("\n".join(condense_session(p) for p in ordered), limit)
