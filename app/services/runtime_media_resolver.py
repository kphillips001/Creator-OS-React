import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeMediaPath:
    path: Path | None
    source: str | None
    exists: bool
    candidates: tuple[tuple[str, Path], ...]

    @property
    def path_string(self) -> str | None:
        return str(self.path) if self.path else None


class RuntimeMediaResolver:
    """
    Resolves the preferred runtime media path for imported Assets.

    This is a compatibility layer for the Local Vault migration. Runtime media
    reads should prefer the Local Vault while legacy file_path remains a safe
    fallback until individual workflows are migrated.
    """

    MEDIA_METADATA_KEY = "media_metadata"
    MEDIA_METADATA_LOCAL_VAULT_KEY = "local_vault_path"
    DIRECT_LOCAL_VAULT_KEY = "local_vault_path"
    LEGACY_FILE_PATH_KEY = "file_path"

    def resolve_original(
        self,
        asset_like: Any,
        *,
        require_exists: bool = False,
    ) -> RuntimeMediaPath:
        candidates = self._candidate_paths(asset_like)

        for source, candidate in candidates:
            if candidate.exists():
                return RuntimeMediaPath(
                    path=candidate,
                    source=source,
                    exists=True,
                    candidates=candidates,
                )

            if not require_exists:
                return RuntimeMediaPath(
                    path=candidate,
                    source=source,
                    exists=False,
                    candidates=candidates,
                )

        return RuntimeMediaPath(
            path=None,
            source=None,
            exists=False,
            candidates=candidates,
        )

    def resolve_original_path(
        self,
        asset_like: Any,
        *,
        require_exists: bool = False,
    ) -> Path | None:
        return self.resolve_original(
            asset_like,
            require_exists=require_exists,
        ).path

    def resolve_original_path_string(
        self,
        asset_like: Any,
        *,
        require_exists: bool = False,
    ) -> str | None:
        return self.resolve_original(
            asset_like,
            require_exists=require_exists,
        ).path_string

    def _candidate_paths(self, asset_like: Any) -> tuple[tuple[str, Path], ...]:
        candidates: list[tuple[str, Path]] = []

        media_metadata = self._coerce_mapping(
            self._get_value(asset_like, self.MEDIA_METADATA_KEY)
        )
        metadata_local_vault_path = media_metadata.get(
            self.MEDIA_METADATA_LOCAL_VAULT_KEY
        )
        self._append_candidate(
            candidates,
            "media_metadata.local_vault_path",
            metadata_local_vault_path,
        )

        self._append_candidate(
            candidates,
            "local_vault_path",
            self._get_value(asset_like, self.DIRECT_LOCAL_VAULT_KEY),
        )
        self._append_candidate(
            candidates,
            "file_path",
            self._get_value(asset_like, self.LEGACY_FILE_PATH_KEY),
        )

        return tuple(candidates)

    @staticmethod
    def _append_candidate(
        candidates: list[tuple[str, Path]],
        source: str,
        raw_path: Any,
    ) -> None:
        if raw_path is None:
            return

        path_value = str(raw_path).strip()
        if not path_value:
            return

        candidates.append((source, Path(path_value).expanduser()))

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
    def _get_value(asset_like: Any, key: str) -> Any:
        if isinstance(asset_like, Mapping):
            return asset_like.get(key)

        return getattr(asset_like, key, None)
