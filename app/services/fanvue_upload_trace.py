"""Safe JSONL tracing for Fanvue upload diagnostics."""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FANVUE_WALL_UPLOAD_TRACE_LOG = Path("logs") / "fanvue_wall_upload_debug.log"
MAX_RESPONSE_TEXT_LENGTH = 12000


def fanvue_upload_trace(event: str, **payload: Any) -> None:
    try:
        FANVUE_WALL_UPLOAD_TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **_sanitize(payload),
        }
        with FANVUE_WALL_UPLOAD_TRACE_LOG.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fanvue_upload_exception(event: str, exc: BaseException, **payload: Any) -> None:
    fanvue_upload_trace(
        event,
        **payload,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )


def fanvue_response_payload(response: Any, *, include_body: bool = True) -> dict[str, Any]:
    payload = {
        "status_code": getattr(response, "status_code", None),
        "headers": dict(getattr(response, "headers", {}) or {}),
    }
    if not include_body:
        return payload

    text = getattr(response, "text", "")
    try:
        payload["json"] = response.json()
    except Exception:
        payload["body"] = _truncate_text(text)
    else:
        payload["body"] = _truncate_text(text)
    return payload


def _truncate_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if len(text) <= MAX_RESPONSE_TEXT_LENGTH:
        return text
    return text[:MAX_RESPONSE_TEXT_LENGTH] + "...<truncated>"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if (
                "token" in key_lower
                or key_lower in {"authorization", "cookie", "set-cookie"}
                or "signature" in key_lower
                or "credential" in key_lower
            ):
                clean[key_text] = "<redacted>"
            else:
                clean[key_text] = _sanitize(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str) and ("X-Amz-Signature=" in value or "X-Amz-Credential=" in value):
        return "<redacted signed url>"
    return value
