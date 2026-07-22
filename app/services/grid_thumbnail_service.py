"""Lazy, source-fingerprinted thumbnails for Asset Library cards."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps

from app.services.local_vault_service import LocalVaultService


class GridThumbnailService:
    MAX_WIDTH = 512
    WEBP_QUALITY = 82
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.Lock] = {}

    def __init__(self, *, local_vault_service: LocalVaultService | None = None):
        self.local_vault = local_vault_service or LocalVaultService()
        self.cache_directory = self.local_vault.path("vault/thumbnails/asset_library")

    def get_or_create(self, source: str | Path, *, identity: str) -> Path:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        stat = source_path.stat()
        freshness = f"{source_path}|{stat.st_size}|{stat.st_mtime_ns}"
        digest = hashlib.sha256(freshness.encode("utf-8")).hexdigest()[:16]
        safe_identity = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(identity)).strip("-")
        target = self.cache_directory / f"{safe_identity or 'image'}-{digest}.webp"
        if target.is_file():
            return target

        lock = self._lock_for(str(target))
        with lock:
            if target.is_file():
                return target
            self.cache_directory.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=self.cache_directory,
                    prefix=f".{target.stem}-",
                    suffix=".tmp.webp",
                    delete=False,
                ) as temporary:
                    temporary_path = Path(temporary.name)
                with Image.open(source_path) as opened:
                    image = ImageOps.exif_transpose(opened)
                    image.thumbnail(
                        (self.MAX_WIDTH, max(1, image.height)),
                        Image.Resampling.LANCZOS,
                    )
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert(
                            "RGBA" if "transparency" in image.info else "RGB"
                        )
                    image.save(
                        temporary_path,
                        format="WEBP",
                        quality=self.WEBP_QUALITY,
                        method=4,
                    )
                os.replace(temporary_path, target)
                temporary_path = None
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
        return target

    @classmethod
    def _lock_for(cls, key: str) -> threading.Lock:
        with cls._locks_guard:
            return cls._locks.setdefault(key, threading.Lock())
