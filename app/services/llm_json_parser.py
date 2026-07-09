"""Reusable JSON parsing helpers for LLM responses."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DEBUG_DIR = Path("data") / "debug"


def extract_llm_json_text(raw_text: str) -> str:
    """Extract a JSON object from plain or Markdown-fenced LLM text."""

    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("LLM response was empty.")

    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object was found in the LLM response.")
    return text[start : end + 1].strip()


def parse_llm_json(
    raw_text: str,
    *,
    model_name: str,
    caller: str,
    debug_dir: str | Path = DEFAULT_DEBUG_DIR,
) -> Any:
    """Parse a JSON object from an LLM response and save failure context."""

    try:
        return json.loads(extract_llm_json_text(raw_text))
    except Exception as exc:
        debug_path = _save_llm_json_parse_failure(
            raw_text=raw_text,
            model_name=model_name,
            caller=caller,
            debug_dir=Path(debug_dir),
        )
        raise ValueError(
            "LLM JSON parser failure: "
            f"{exc}. Raw response saved to {debug_path}"
        ) from exc


def _save_llm_json_parse_failure(
    *,
    raw_text: str,
    model_name: str,
    caller: str,
    debug_dir: Path,
) -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / "grok_last_response.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "caller": caller,
        "raw_response": str(raw_text or ""),
    }
    debug_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return debug_path
