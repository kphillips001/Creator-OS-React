"""Canonical PostgreSQL-safe sanitizer for Developer Agent persistence."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


BINARY_SUFFIXES = frozenset({
    ".dump", ".bak", ".bin", ".db", ".sqlite", ".sqlite3", ".zip",
    ".gz", ".7z", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov",
})


def sanitize_developer_agent_value(value: Any) -> Any:
    """Return a recursively PostgreSQL text/JSON-safe representation."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, bytes):
        return {"kind": "binary_value", "size_bytes": len(value)}
    if isinstance(value, bytearray):
        return {"kind": "binary_value", "size_bytes": len(value)}
    if isinstance(value, memoryview):
        return {"kind": "binary_value", "size_bytes": value.nbytes}
    if isinstance(value, Path):
        if value.suffix.lower() in BINARY_SUFFIXES:
            metadata = {
                "path": str(value),
                "kind": "binary_file",
                "size_bytes": None,
            }
            try:
                metadata["size_bytes"] = value.stat().st_size
            except OSError:
                pass
            return metadata
        return sanitize_developer_agent_value(str(value))
    if isinstance(value, Mapping):
        path_value = value.get("path") or value.get("file_path")
        if isinstance(path_value, (str, Path)) and Path(str(path_value)).suffix.lower() in BINARY_SUFFIXES:
            raw = value.get("content", value.get("data", value.get("bytes")))
            size = value.get("size_bytes")
            if size is None and isinstance(raw, (str, bytes, bytearray, memoryview)):
                size = len(raw)
            return {
                "path": sanitize_developer_agent_value(str(path_value)),
                "kind": "binary_file",
                "size_bytes": size,
            }
        return {
            sanitize_developer_agent_value(str(key)): sanitize_developer_agent_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_developer_agent_value(item) for item in value]
    if isinstance(value, BaseException):
        return sanitize_developer_agent_value(str(value) or type(value).__name__)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_developer_agent_value(str(value))
