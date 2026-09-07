"""Bounded retention for file-backed Creator-OS runtime diagnostics."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogRetentionResult:
    path: str
    bytes_before: int
    bytes_after: int
    bytes_removed: int
    rotated: bool


class LogRetentionService:
    """Keep active log paths usable while bounding retained diagnostic bytes.

    Creator-OS launches subprocesses with stdout/stderr redirected directly to
    files.  Copy/truncate is therefore used instead of renaming the active file:
    inherited process handles keep writing to the canonical path after a sweep.
    The launcher performs the initial sweep while services are stopped; the
    supervisor monitor performs later sweeps before a file can grow indefinitely.
    """

    DEFAULT_MAX_BYTES = 16 * 1024 * 1024
    DEFAULT_BACKUP_COUNT = 2

    def __init__(self, log_root: Path, *, max_bytes: int = DEFAULT_MAX_BYTES,
                 backup_count: int = DEFAULT_BACKUP_COUNT):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if backup_count < 1:
            raise ValueError("backup_count must be at least one")
        self.log_root = Path(log_root)
        self.max_bytes = int(max_bytes)
        self.backup_count = int(backup_count)

    def enforce(self) -> tuple[LogRetentionResult, ...]:
        if not self.log_root.is_dir():
            return ()
        return tuple(self.enforce_file(path) for path in sorted(self.log_root.rglob("*.log")))

    def enforce_file(self, path: Path) -> LogRetentionResult:
        path = Path(path)
        before = path.stat().st_size
        if before <= self.max_bytes:
            return LogRetentionResult(str(path), before, before, 0, False)

        retained = self._tail(path, self.max_bytes)
        self._shift_backups(path)
        backup = self._backup_path(path, 1)
        temporary = backup.with_name(backup.name + ".tmp")
        temporary.write_bytes(retained)
        os.replace(temporary, backup)

        # Preserve the inode/path used by inherited stdout/stderr handles.
        with path.open("r+b") as active:
            active.truncate(0)
        after = path.stat().st_size
        return LogRetentionResult(str(path), before, after, before - after, True)

    def maximum_retained_bytes_per_log(self) -> int:
        return self.max_bytes * (self.backup_count + 1)

    def _shift_backups(self, path: Path) -> None:
        oldest = self._backup_path(path, self.backup_count)
        oldest.unlink(missing_ok=True)
        for number in range(self.backup_count - 1, 0, -1):
            source = self._backup_path(path, number)
            if source.exists():
                os.replace(source, self._backup_path(path, number + 1))

    @staticmethod
    def _tail(path: Path, limit: int) -> bytes:
        with path.open("rb") as source:
            source.seek(-limit, os.SEEK_END)
            retained = source.read(limit)
        # A byte-size boundary can land inside a UTF-8 codepoint or partial
        # diagnostic line. Keep only complete lines at the retained boundary.
        _, separator, complete = retained.partition(b"\n")
        return complete if separator else retained

    @staticmethod
    def _backup_path(path: Path, number: int) -> Path:
        return path.with_name(f"{path.name}.{number}")
