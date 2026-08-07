"""Temporary, secret-safe diagnostics for Ava generation pipeline comparison."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class GenerationRequestDiagnosticService:
    """Persist ordered runtime stages for the two in-scope workflows only."""

    SUPPORTED_ORIGINS = {"autonomous_inspiration", "manual_creative_concept"}
    REDACTED_KEYS = {
        "api_key", "apikey", "authorization", "cookie", "password",
        "secret", "token", "access_token", "refresh_token",
    }
    storage_path = Path("data/developer_diagnostics/generation_request_traces.json")
    _lock = threading.Lock()

    def record(self, *, trace_id: str | None, workflow_origin: str | None,
               stage: str, value: Any) -> None:
        identifier = str(trace_id or "").strip()
        origin = str(workflow_origin or "").strip()
        if not identifier or origin not in self.SUPPORTED_ORIGINS:
            return
        event = {
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "stage": str(stage),
            "value": self._sanitize(value),
        }
        with self._lock:
            traces = self._read()
            trace = traces.setdefault(identifier, {
                "traceId": identifier, "workflowOrigin": origin, "events": [],
            })
            trace["workflowOrigin"] = origin
            trace.setdefault("events", []).append(event)
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.storage_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8",
            )
            temporary.replace(self.storage_path)

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    @classmethod
    def _sanitize(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): "[REDACTED]"
                if str(key).lower() in cls.REDACTED_KEYS
                else cls._sanitize(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [cls._sanitize(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if hasattr(value, "model_dump"):
            return cls._sanitize(value.model_dump())
        if hasattr(value, "__dict__"):
            return cls._sanitize(vars(value))
        return str(value)
