"""Explicit, atomic compatibility snapshots for the canonical Generation Library."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.database import get_db_connection


class GenerationLibrarySnapshotService:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def create(self, output_dir: str | Path = "backups/generation_library", *, retain: int = 5) -> dict:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".generation-library-{uuid4().hex}.tmp"
        digest = hashlib.sha256()
        count = 0
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cursor.execute("SELECT revision FROM generation_library_canonical_state WHERE store_name='generation_library'")
                state = cursor.fetchone()
                revision = int(state["revision"] if state else 0)
                cursor.execute("SELECT record_payload FROM generation_library_records ORDER BY created_at,image_id")
                with open(temporary, "wb") as target:
                    target.write(b"[")
                    while True:
                        rows = cursor.fetchmany(100)
                        if not rows: break
                        for row in rows:
                            encoded = json.dumps(row["record_payload"], ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
                            if count: target.write(b",")
                            target.write(encoded); digest.update(encoded); count += 1
                    target.write(b"]"); target.flush(); os.fsync(target.fileno())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = directory / f"generated_images-r{revision}-{stamp}.json"
        os.replace(temporary, snapshot)
        verified_count = self._verify(snapshot)
        if verified_count != count:
            snapshot.unlink(missing_ok=True)
            raise RuntimeError(f"Snapshot verification failed: expected {count}, found {verified_count}.")
        manifest = snapshot.with_suffix(".manifest.json")
        manifest.write_text(json.dumps({
            "schema": "generation_library_snapshot_v1", "canonicalRevision": revision,
            "createdAt": datetime.now(timezone.utc).isoformat(), "recordCount": count,
            "recordPayloadSha256": digest.hexdigest(), "snapshotFile": snapshot.name,
            "snapshotBytes": snapshot.stat().st_size,
        }, indent=2), encoding="utf-8")
        self._prune(directory, retain=max(1, int(retain)))
        return json.loads(manifest.read_text(encoding="utf-8"))

    @staticmethod
    def _verify(path: Path) -> int:
        with open(path, "r", encoding="utf-8") as source:
            payload = json.load(source)
        if not isinstance(payload, list) or not all(isinstance(item, dict) and item.get("image_id") for item in payload):
            raise RuntimeError("Snapshot is not a valid Generation Library record array.")
        return len(payload)

    @staticmethod
    def _prune(directory: Path, *, retain: int) -> None:
        snapshots = sorted(
            (path for path in directory.glob("generated_images-r*.json") if not path.name.endswith(".manifest.json")),
            key=lambda path: path.stat().st_mtime, reverse=True,
        )
        for snapshot in snapshots[retain:]:
            snapshot.unlink(missing_ok=True)
            snapshot.with_suffix(".manifest.json").unlink(missing_ok=True)
