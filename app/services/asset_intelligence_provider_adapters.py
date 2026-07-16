"""Thin adapters over Creator OS vision integrations for Phase 2A."""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping

from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode,
    AssetIntelligenceProviderRequest,
    AssetIntelligenceProviderResponse,
    ProviderExecutionStatus,
)
from app.services.llm_json_parser import parse_llm_json
from app.config import GROK_VISION_MODEL


_KISS_FIELDS = {
    "short_description", "tags", "themes", "safety_classification",
    "quality_score", "keywords",
}


def _clean_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _quality(value: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


class _CallableAdapter:
    supported_media_types = frozenset({"image"})

    def __init__(self, runner: Callable[..., Any] | None = None) -> None:
        self._runner = runner

    def is_ready(self) -> bool:
        return True

    def analyze(self, request: AssetIntelligenceProviderRequest) -> AssetIntelligenceProviderResponse:
        started = datetime.now(timezone.utc)
        clock = monotonic()
        try:
            raw = self._analyze(Path(request.managed_media_path))
            if isinstance(raw, Mapping) and raw.get("error"):
                raise RuntimeError(str(raw["error"]))
            if isinstance(raw, (list, tuple)) and any(
                isinstance(item, Mapping) and item.get("error") for item in raw
            ):
                raise RuntimeError(str(next(item["error"] for item in raw if isinstance(item, Mapping) and item.get("error"))))
            normalized = dict(self.normalize(raw))
            status = ProviderExecutionStatus.SUCCEEDED
            error_code = None
            error_message = None
        except FileNotFoundError as exc:
            raw, normalized = None, {}
            status = ProviderExecutionStatus.FAILED
            error_code, error_message = AssetIntelligenceErrorCode.MEDIA_NOT_FOUND, str(exc)
        except Exception as exc:
            raw, normalized = None, {}
            status = ProviderExecutionStatus.FAILED
            error_code, error_message = AssetIntelligenceErrorCode.PROVIDER_UNAVAILABLE, str(exc)
        completed = datetime.now(timezone.utc)
        return AssetIntelligenceProviderResponse(
            run_id=request.run_id, asset_id=request.asset_id,
            provider_name=self.provider_name, provider_version=self.provider_version,
            status=status, raw_response=raw, normalized_fields=normalized,
            field_confidence={key: 0.8 for key in normalized},
            error_code=error_code, error_message=error_message,
            started_at=started, completed_at=completed,
            duration_ms=max(0, round((monotonic() - clock) * 1000)),
        )

    def _analyze(self, path: Path) -> Any:
        if not path.is_file():
            raise FileNotFoundError(path)
        return self._runner(path) if self._runner else self._default_runner(path)


class GptVisionAssetIntelligenceAdapter(_CallableAdapter):
    provider_name = "gpt-vision"
    provider_version = "gpt-4.1-mini"

    @staticmethod
    def _default_runner(path: Path):
        from app.services.content_classification_service import run_gpt_vision
        return run_gpt_vision(path, "teaser_image")

    def normalize(self, raw_response: Any) -> Mapping[str, Any]:
        raw = dict(raw_response or {})
        return {
            "short_description": raw.get("short_description") or raw.get("short_safe_summary"),
            "tags": _clean_list(raw.get("tags") or raw.get("suggested_tags")),
            "themes": _clean_list(raw.get("themes") or raw.get("detected_themes")),
            "safety_classification": raw.get("safety_classification") or raw.get("classification"),
            "quality_score": _quality(raw.get("quality_score") or raw.get("confidence")),
            "keywords": _clean_list(raw.get("keywords") or raw.get("suggested_tags")),
        }


class NudeNetAssetIntelligenceAdapter(_CallableAdapter):
    provider_name = "nudenet"
    provider_version = "nudenet-existing"

    @staticmethod
    def _default_runner(path: Path):
        from app.services.content_classification_service import run_nudenet
        return run_nudenet(path)

    def normalize(self, raw_response: Any) -> Mapping[str, Any]:
        detections = tuple(item for item in (raw_response or ()) if isinstance(item, Mapping))
        labels = _clean_list([item.get("class") for item in detections])
        exposed = any("EXPOSED" in label for label in labels)
        explicit = any(token in label for label in labels for token in ("GENITALIA", "ANUS"))
        safety = "EXPLICIT" if explicit else "NUDITY" if exposed else "SAFE"
        normalized = {"safety_classification": safety}
        if labels:
            normalized["keywords"] = labels
        return normalized


class GrokVisionAssetIntelligenceAdapter(_CallableAdapter):
    provider_name = "grok-vision"
    provider_version = GROK_VISION_MODEL

    def is_ready(self) -> bool:
        return bool(os.getenv("GROK_API_KEY", "").strip()) or self._runner is not None

    @staticmethod
    def _default_runner(path: Path):
        from openai import OpenAI

        api_key = os.getenv("GROK_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROK_API_KEY is not configured.")
        mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
        image_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('utf-8')}"
        client = OpenAI(api_key=api_key, base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"))
        response = client.responses.create(
            model=GROK_VISION_MODEL,
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": (
                    "Analyze this image for an asset inventory. Return only JSON with: "
                    "short_description (string), tags (string array), themes (string array), "
                    "safety_classification (string), quality_score (0 to 1 number), keywords (string array)."
                )},
                {"type": "input_image", "image_url": image_url},
            ]}],
        )
        return parse_llm_json(response.output_text, model_name="grok-vision", caller="GrokVisionAssetIntelligenceAdapter")

    def normalize(self, raw_response: Any) -> Mapping[str, Any]:
        raw = dict(raw_response or {})
        return {
            key: _clean_list(raw.get(key)) if key in {"tags", "themes", "keywords"}
            else _quality(raw.get(key)) if key == "quality_score" else raw.get(key)
            for key in _KISS_FIELDS
            if raw.get(key) is not None
        }
