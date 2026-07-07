"""Media Processing service facade."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping
from datetime import datetime, timezone

from app.services.blur_service import generate_blurred_preview
from app.services.local_vault_service import LocalVaultService


class MediaProcessingService:
    """Owns media derivative generation for Creator OS workflows."""

    BLURRED_PREVIEW = "blurred_preview"
    _DERIVATIVE_ALIASES = {
        "blur": BLURRED_PREVIEW,
        "blurred": BLURRED_PREVIEW,
        "blurred_preview": BLURRED_PREVIEW,
    }

    def __init__(
        self,
        blur_generator: Callable[..., str] = generate_blurred_preview,
        local_vault_service: LocalVaultService | None = None,
    ):
        self._blur_generator = blur_generator
        self.local_vault_service = local_vault_service or LocalVaultService()
        self.local_vault_service.initialize()

    def generate_blurred_preview(self, media: Any, **kwargs) -> str:
        return self.generate_derivative(
            media,
            self.BLURRED_PREVIEW,
            **kwargs,
        )

    def generate_derivative(
        self,
        asset_or_path: Any,
        derivative_type: str,
        **kwargs,
    ) -> str:
        normalized_type = self._normalize_derivative_type(derivative_type)
        if normalized_type == self.BLURRED_PREVIEW:
            generation_kwargs = {
                **kwargs,
                "output_dir": kwargs.get(
                    "output_dir",
                    self.derivative_directory(normalized_type),
                ),
            }
            return self._blur_generator(asset_or_path, **generation_kwargs)
        raise ValueError(
            f"Unsupported derivative type: {derivative_type}"
        )

    def generate_derivative_metadata(
        self,
        asset_or_path: Any,
        derivative_type: str,
        **kwargs,
    ) -> dict[str, Any]:
        derivative_path = self.generate_derivative(
            asset_or_path,
            derivative_type,
            **kwargs,
        )
        return self.build_derivative_metadata(
            derivative_path=derivative_path,
            derivative_type=derivative_type,
        )

    def get_or_create_derivative(
        self,
        asset_or_path: Any,
        derivative_type: str,
        **kwargs,
    ) -> str:
        existing = self.resolve_derivative(
            asset_or_path,
            derivative_type,
        )
        if existing:
            return str(existing)
        return self.generate_derivative(
            asset_or_path,
            derivative_type,
            **kwargs,
        )

    def resolve_derivative(
        self,
        asset_or_path: Any,
        derivative_type: str,
    ) -> str | None:
        normalized_type = self._normalize_derivative_type(derivative_type)
        if normalized_type != self.BLURRED_PREVIEW:
            return None

        return self._resolve_blurred_preview(asset_or_path)

    def regenerate_derivatives(
        self,
        asset_or_path: Any,
        derivative_types: list[str] | tuple[str, ...] | None = None,
        **kwargs,
    ) -> dict[str, str]:
        results = {}
        for derivative_type in derivative_types or (self.BLURRED_PREVIEW,):
            normalized_type = self._normalize_derivative_type(derivative_type)
            if not normalized_type:
                raise ValueError(
                    f"Unsupported derivative type: {derivative_type}"
                )
            generation_kwargs = {
                **kwargs,
                "overwrite": True,
            }
            results[normalized_type] = self.generate_derivative(
                asset_or_path,
                normalized_type,
                **generation_kwargs,
            )
        return results

    def delete_derivatives(
        self,
        asset_or_path: Any,
        derivative_types: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, bool]:
        results = {}
        for derivative_type in derivative_types or (self.BLURRED_PREVIEW,):
            normalized_type = self._normalize_derivative_type(derivative_type)
            if not normalized_type:
                raise ValueError(
                    f"Unsupported derivative type: {derivative_type}"
                )
            derivative_path = self.resolve_derivative(
                asset_or_path,
                normalized_type,
            )
            if not derivative_path:
                results[normalized_type] = False
                continue
            Path(derivative_path).unlink(missing_ok=True)
            results[normalized_type] = True
        return results

    def build_derivative_metadata(
        self,
        *,
        derivative_path: str | Path,
        derivative_type: str,
        storage: str | None = None,
        generated_at: str | None = None,
        source: str = "media_processing_service",
    ) -> dict[str, Any]:
        normalized_type = self._normalize_derivative_type(derivative_type)
        if normalized_type != self.BLURRED_PREVIEW:
            raise ValueError(
                f"Unsupported derivative type: {derivative_type}"
            )
        path = str(derivative_path)
        return {
            "path": path,
            "type": "blur",
            "storage": storage or self._storage_for_path(path),
            "generated_at": generated_at
            or datetime.now(timezone.utc).isoformat(),
            "source": source,
        }

    def normalize_derivative_metadata(
        self,
        derivative_metadata: Any,
        *,
        derivative_type: str,
    ) -> dict[str, Any]:
        normalized_type = self._normalize_derivative_type(derivative_type)
        if normalized_type != self.BLURRED_PREVIEW:
            raise ValueError(
                f"Unsupported derivative type: {derivative_type}"
            )
        if isinstance(derivative_metadata, Mapping):
            path = self._extract_path_value(derivative_metadata)
            if not path:
                return {}
            return {
                "path": str(path),
                "type": derivative_metadata.get("type") or "blur",
                "storage": derivative_metadata.get("storage")
                or self._storage_for_path(path),
                "generated_at": derivative_metadata.get("generated_at"),
                "source": derivative_metadata.get("source")
                or "media_processing_service",
            }
        if derivative_metadata:
            return self.build_derivative_metadata(
                derivative_path=str(derivative_metadata),
                derivative_type=normalized_type,
                generated_at=None,
            )
        return {}

    def merge_derivative_metadata(
        self,
        media_metadata: Any,
        *,
        derivative_type: str,
        derivative_metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_type = self._normalize_derivative_type(derivative_type)
        if normalized_type != self.BLURRED_PREVIEW:
            raise ValueError(
                f"Unsupported derivative type: {derivative_type}"
            )
        merged = dict(self._coerce_mapping(media_metadata))
        derivatives = dict(self._coerce_mapping(merged.get("derivatives")))
        normalized_metadata = self.normalize_derivative_metadata(
            derivative_metadata,
            derivative_type=normalized_type,
        )
        derivatives["blur"] = normalized_metadata
        derivatives["blurred_preview"] = normalized_metadata
        merged["derivatives"] = derivatives
        return merged

    def _resolve_blurred_preview(self, asset_or_path: Any) -> str | None:
        media_metadata = self._coerce_mapping(
            self._get_value(asset_or_path, "media_metadata")
        )
        derivatives = self._coerce_mapping(
            media_metadata.get("derivatives")
        )
        for key in ("blurred_preview", "blur"):
            resolved = self._resolve_existing_path(
                self._extract_path_value(derivatives.get(key))
            )
            if resolved:
                return str(resolved)

        resolved = self._resolve_local_vault_blurred_preview(asset_or_path)
        if resolved:
            return str(resolved)

        direct_preview = self._get_value(asset_or_path, "blurred_preview_path")
        resolved = self._resolve_existing_path(direct_preview)
        if resolved:
            return str(resolved)
        return None

    def derivative_directory(self, derivative_type: str) -> Path:
        normalized_type = self._normalize_derivative_type(derivative_type)
        if normalized_type == self.BLURRED_PREVIEW:
            return self.local_vault_service.path("vault/blurred")
        raise ValueError(
            f"Unsupported derivative type: {derivative_type}"
        )

    def _resolve_local_vault_blurred_preview(
        self,
        asset_or_path: Any,
    ) -> Path | None:
        stem = self._original_media_stem(asset_or_path)
        suffix = self._original_media_suffix(asset_or_path)
        if not stem or not suffix:
            return None
        return self._resolve_existing_path(
            self.derivative_directory(self.BLURRED_PREVIEW)
            / f"{stem}_blurred{suffix}"
        )

    def _original_media_stem(self, asset_or_path: Any) -> str | None:
        original_path = self._extract_original_path(asset_or_path)
        if original_path:
            return Path(str(original_path)).stem
        return None

    def _original_media_suffix(self, asset_or_path: Any) -> str | None:
        original_path = self._extract_original_path(asset_or_path)
        if original_path:
            return Path(str(original_path)).suffix
        return None

    def _extract_original_path(self, asset_or_path: Any) -> Any:
        if isinstance(asset_or_path, (str, Path)):
            return asset_or_path
        media_metadata = self._coerce_mapping(
            self._get_value(asset_or_path, "media_metadata")
        )
        return (
            media_metadata.get("local_vault_path")
            or self._get_value(asset_or_path, "local_vault_path")
            or self._get_value(asset_or_path, "file_path")
        )

    def _storage_for_path(self, path: str | Path) -> str:
        raw_path = Path(str(path)).expanduser()
        try:
            raw_path.resolve().relative_to(
                self.derivative_directory(self.BLURRED_PREVIEW).resolve()
            )
            return "local_vault"
        except ValueError:
            pass
        return "legacy"

    def _normalize_derivative_type(self, derivative_type: str | None) -> str | None:
        if not derivative_type:
            return None
        return self._DERIVATIVE_ALIASES.get(str(derivative_type).strip().lower())

    @staticmethod
    def _get_value(asset_like: Any, key: str) -> Any:
        if isinstance(asset_like, Mapping):
            return asset_like.get(key)
        return getattr(asset_like, key, None)

    @staticmethod
    def _coerce_mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, Mapping):
                return parsed
        return {}

    @staticmethod
    def _extract_path_value(value: Any) -> Any:
        if isinstance(value, Mapping):
            for key in ("path", "file_path", "local_path"):
                if value.get(key):
                    return value.get(key)
            return None
        return value

    @staticmethod
    def _resolve_existing_path(value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value)).expanduser()
        candidates = (
            path,
            Path.cwd() / path,
            Path("data/previews") / path.name,
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None
