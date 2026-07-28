"""Read-only, in-memory inspection of allowlisted official Fanvue endpoints."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.services.fanvue_official_client import FanvueAPIError, FanvueOfficialClient


_SENSITIVE_KEY = re.compile(
    r"(?:access|refresh|id)[_-]?token|authorization|cookie|client[_-]?secret",
    re.IGNORECASE,
)


def redact_sensitive(value: Any, key: str | None = None) -> Any:
    """Recursively redact credentials while retaining provider business IDs."""
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_sensitive(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


class FanvueAPIExplorerService:
    """Execute one GET against the existing authenticated Fanvue client."""

    API_VERSION = FanvueOfficialClient.API_VERSION

    def __init__(self, *, client_factory=None, clock=time.perf_counter) -> None:
        self.client_factory = client_factory or FanvueOfficialClient
        self.clock = clock

    def inspect(
        self,
        *,
        fanvue_account_id: int,
        operation: str,
        scopes: tuple[str, ...] = (),
        start_date: str | None = None,
        end_date: str | None = None,
        page_size: int | None = None,
        media_uuid: str | None = None,
    ) -> dict[str, Any]:
        endpoint, params = self._request(
            operation=operation,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            media_uuid=media_uuid,
        )
        started = self.clock()
        status = 0
        headers: dict[str, Any] = {}
        body: Any = None
        error: str | None = None
        try:
            response = self.client_factory(fanvue_account_id).request(
                "GET", endpoint, params=params or None, retry_429=False
            )
            status = int(response.status_code)
            headers = dict(response.headers)
            try:
                body = response.json()
            except Exception:
                body = response.text
        except FanvueAPIError as exc:
            status = int(exc.status_code or 0)
            body = exc.body
            error = str(exc)
            if exc.retry_after is not None:
                headers["Retry-After"] = exc.retry_after
        except Exception as exc:
            error = str(exc)
            body = {"error": type(exc).__name__, "message": str(exc)}

        elapsed_ms = round((self.clock() - started) * 1000, 2)
        safe_body = redact_sensitive(body)
        safe_headers = redact_sensitive(headers)
        pagination = self._pagination(safe_body)
        return {
            "endpoint": endpoint,
            "requestParams": params,
            "httpStatus": status,
            "elapsedMs": elapsed_ms,
            "recordCount": self._record_count(safe_body),
            "cursor": pagination["cursor"],
            "nextPage": pagination["nextPage"],
            "pagination": pagination["metadata"],
            "apiVersion": self.API_VERSION,
            "oauthScopes": sorted(set(scopes)),
            "headers": safe_headers,
            "body": safe_body,
            "rawJson": self._json_text(safe_body),
            "error": error,
        }

    @staticmethod
    def _request(
        *,
        operation: str,
        start_date: str | None,
        end_date: str | None,
        page_size: int | None,
        media_uuid: str | None,
    ) -> tuple[str, dict[str, Any]]:
        normalized = str(operation or "").strip().lower()
        if normalized == "earnings":
            params: dict[str, Any] = {}
            if start_date:
                params["startDate"] = start_date
            if end_date:
                params["endDate"] = end_date
            if page_size is not None:
                params["limit"] = max(1, min(100, int(page_size)))
            return "/insights/earnings", params
        if normalized == "media-links":
            return "/media-links", {}
        if normalized == "current-user":
            return "/users/me", {}
        if normalized == "media":
            if not media_uuid:
                raise ValueError("A Media UUID is required.")
            try:
                safe_uuid = str(UUID(str(media_uuid)))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError("Media UUID must be a valid UUID.") from exc
            return f"/media/{safe_uuid}", {}
        raise ValueError(f"Unsupported Fanvue explorer operation: {operation}")

    @staticmethod
    def _record_count(body: Any) -> int | None:
        if isinstance(body, list):
            return len(body)
        if not isinstance(body, Mapping):
            return None
        for key in ("items", "data", "results"):
            value = body.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, Mapping):
                nested = value.get("items")
                if isinstance(nested, list):
                    return len(nested)
        return 1

    @staticmethod
    def _pagination(body: Any) -> dict[str, Any]:
        if not isinstance(body, Mapping):
            return {"cursor": None, "nextPage": None, "metadata": {}}
        candidates = [
            body.get("pagination"),
            body.get("meta"),
            body.get("metadata"),
            body.get("data") if isinstance(body.get("data"), Mapping) else None,
        ]
        metadata = next(
            (dict(value) for value in candidates if isinstance(value, Mapping)),
            {},
        )
        cursor = (
            metadata.get("cursor")
            or metadata.get("nextCursor")
            or body.get("nextCursor")
            or body.get("cursor")
        )
        next_page = (
            metadata.get("nextPage")
            or metadata.get("next")
            or body.get("nextPage")
            or body.get("next")
        )
        return {"cursor": cursor, "nextPage": next_page, "metadata": metadata}

    @staticmethod
    def _json_text(body: Any) -> str:
        if isinstance(body, str):
            return body
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str)
