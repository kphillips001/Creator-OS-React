"""Resolve canonical local assets to durable, verified public references."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.repositories.hosted_asset_reference_repository import HostedAssetReferenceRepository


LOGGER = logging.getLogger("creator_os.transport")


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class HostedAssetReferenceError(RuntimeError):
    stage = "canonical_reference_upload"
    retryable = True
    may_have_been_accepted = False


class HostedAssetReferenceService:
    def __init__(self, *, repository=None, http_client=None, sleep=time.sleep):
        self.repository = repository or HostedAssetReferenceRepository()
        self.http_client = http_client or requests
        self.sleep = sleep
        self.verification_ttl = timedelta(seconds=max(0, _number("HOSTED_REFERENCE_VERIFY_TTL_SECONDS", 86400)))
        self.maximum_age = timedelta(seconds=max(0, _number("HOSTED_REFERENCE_MAX_AGE_SECONDS", 518400)))
        self.verify_timeout = max(1, _number("HOSTED_REFERENCE_VERIFY_TIMEOUT_SECONDS", 15))
        self.retry_delays = self._retry_delays()

    @staticmethod
    def checksum(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest().upper()

    @staticmethod
    def _retry_delays() -> tuple[float, ...]:
        count = max(1, int(_number("HOSTED_REFERENCE_RETRY_COUNT", 3)))
        configured = [value.strip() for value in os.getenv("HOSTED_REFERENCE_RETRY_BACKOFF_SECONDS", "2,5").split(",")]
        delays = []
        for value in configured:
            try:
                delays.append(max(0, float(value)))
            except ValueError:
                continue
        while len(delays) < count - 1:
            delays.append(2 ** (len(delays) + 1))
        return tuple(delays[:count - 1])

    def resolve(self, *, asset_id: int, source_path: str, host_name: str, uploader) -> str:
        path = Path(source_path)
        if not path.is_file():
            raise HostedAssetReferenceError(f"Canonical reference file was not found: {path}")
        checksum = self.checksum(path)
        current = self.repository.find_current(
            asset_id=asset_id, host_name=host_name, source_checksum=checksum,
        )
        if current and self._expired(getattr(current, "created_at", None)):
            self.repository.mark_stale(
                current.reference_id,
                error_code="hosted_reference_expiring",
                error_message="The provider-hosted reference reached its safe refresh age.",
            )
            current = None
        if current and self._recently_verified(current.verified_at):
            self.repository.touch_used(current.reference_id)
            self._log("canonical_reference_resolution", host_name, asset_id, 1, 0, "cache_hit")
            return current.hosted_url
        if current:
            try:
                self.verify(current.hosted_url, asset_id=asset_id)
                self.repository.touch_verified(current.reference_id)
                return current.hosted_url
            except HostedAssetReferenceError as exc:
                self.repository.mark_stale(
                    current.reference_id, error_code="hosted_reference_unreachable", error_message=str(exc),
                )
        try:
            hosted_url = uploader(path)
            self.verify(hosted_url, asset_id=asset_id)
            self.repository.save_ready(
                asset_id=asset_id, host_name=host_name, hosted_url=hosted_url,
                source_checksum=checksum, source_path=str(path),
            )
            return hosted_url
        except HostedAssetReferenceError:
            raise
        except Exception as exc:
            raise HostedAssetReferenceError(
                "Could not host the canonical reference after 3 attempts. Retry this frame."
            ) from exc

    def cached_url(self, *, asset_id: int, source_path: str, host_name: str) -> str | None:
        path = Path(source_path)
        if not path.is_file():
            return None
        current = self.repository.find_current(
            asset_id=asset_id, host_name=host_name, source_checksum=self.checksum(path),
        )
        if (
            not current
            or self._expired(getattr(current, "created_at", None))
            or not self._recently_verified(current.verified_at)
        ):
            return None
        self.repository.touch_used(current.reference_id)
        return current.hosted_url

    def verify(self, hosted_url: str, *, asset_id: int) -> None:
        if not hosted_url or urlparse(hosted_url).scheme != "https":
            raise HostedAssetReferenceError("Hosted canonical reference did not return a valid HTTPS URL.")
        attempts = len(self.retry_delays) + 1
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                response = self.http_client.get(
                    hosted_url, headers={"Range": "bytes=0-0", "User-Agent": "Creator-OS"},
                    stream=True, timeout=self.verify_timeout,
                )
                status = int(response.status_code)
                if status in {200, 206}:
                    content_type = str(getattr(response, "headers", {}).get("Content-Type") or "").lower()
                    content_length = str(getattr(response, "headers", {}).get("Content-Length") or "").strip()
                    if content_type and not content_type.startswith("image/"):
                        raise HostedAssetReferenceError(
                            f"Hosted canonical reference returned non-image content ({content_type})."
                        )
                    if content_length.isdigit() and int(content_length) <= 0:
                        raise HostedAssetReferenceError("Hosted canonical reference returned an empty image payload.")
                    self._log("canonical_reference_verify", urlparse(hosted_url).netloc, asset_id,
                              attempt, time.perf_counter() - started, "success", status=status)
                    return
                if not self._retryable_status(status):
                    raise HostedAssetReferenceError(f"Hosted canonical reference verification returned HTTP {status}.")
                error = RuntimeError(f"HTTP {status}")
            except HostedAssetReferenceError:
                raise
            except Exception as exc:
                error = exc
                if not self._retryable_exception(exc):
                    raise HostedAssetReferenceError("Hosted canonical reference verification failed.") from exc
            retry = attempt < attempts
            self._log("canonical_reference_verify", urlparse(hosted_url).netloc, asset_id,
                      attempt, time.perf_counter() - started, "retry" if retry else "failed",
                      error=error, retry=retry)
            if not retry:
                raise HostedAssetReferenceError("Hosted canonical reference could not be verified after 3 attempts.") from error
            self.sleep(self.retry_delays[attempt - 1])

    def _recently_verified(self, value: datetime | None) -> bool:
        if value is None:
            return False
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - value <= self.verification_ttl

    def _expired(self, value: datetime | None) -> bool:
        if value is None or self.maximum_age <= timedelta(0):
            return False
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - value >= self.maximum_age

    @staticmethod
    def _retryable_status(status: int) -> bool:
        return status in {408, 429, 502, 503, 504}

    @staticmethod
    def _retryable_exception(exc: Exception) -> bool:
        return isinstance(exc, (requests.ConnectionError, requests.Timeout, ConnectionResetError, TimeoutError))

    @staticmethod
    def _log(stage, host, asset_id, attempt, elapsed, outcome, *, status=None, error=None, retry=False):
        LOGGER.info(
            "transport stage=%s host=%s asset_id=%s attempt=%s elapsed_ms=%s outcome=%s http_status=%s error_code=%s retry=%s",
            stage, host, asset_id, attempt, round(elapsed * 1000, 2), outcome, status,
            error.__class__.__name__ if error else None, retry,
        )
