"""Read-only, provider-authoritative API balance aggregation."""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import requests


@dataclass(frozen=True)
class ProviderBalance:
    provider: str
    display_name: str
    status: str
    balance: Decimal | None = None
    currency: str | None = None
    unit: str | None = None
    authoritative: bool = False
    checked_at: datetime | None = None
    last_successful_at: datetime | None = None
    error_category: str | None = None

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["displayName"] = value.pop("display_name")
        checked_at = value.pop("checked_at")
        last_successful_at = value.pop("last_successful_at")
        value["checkedAt"] = checked_at.isoformat() if checked_at else None
        value["lastSuccessfulAt"] = last_successful_at.isoformat() if last_successful_at else None
        value["errorCategory"] = value.pop("error_category")
        value["balance"] = str(self.balance) if self.balance is not None else None
        return value


class BalanceAdapter:
    provider = ""
    display_name = ""

    def fetch(self, now: datetime) -> ProviderBalance:
        raise NotImplementedError

    def unavailable(self, now: datetime, category: str) -> ProviderBalance:
        return ProviderBalance(self.provider, self.display_name, "UNAVAILABLE", checked_at=now,
                               error_category=category)


class WaveSpeedBalanceAdapter(BalanceAdapter):
    provider, display_name = "WAVESPEED", "WaveSpeed"
    endpoint = "https://api.wavespeed.ai/api/v3/balance"

    def __init__(self, session=requests, api_key: str | None = None):
        self.session = session
        self.api_key = (api_key if api_key is not None else os.getenv("WAVESPEED_API_KEY", "")).strip()

    def fetch(self, now: datetime) -> ProviderBalance:
        if not self.api_key:
            return ProviderBalance(self.provider, self.display_name, "CREDENTIAL_REQUIRED", checked_at=now,
                                   error_category="MISSING_CREDENTIAL")
        try:
            response = self.session.get(self.endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=(3.05, 8))
            if response.status_code in (401, 403):
                return ProviderBalance(self.provider, self.display_name, "CREDENTIAL_REQUIRED", checked_at=now,
                                       error_category="AUTHENTICATION")
            response.raise_for_status()
            payload = response.json()
            amount = Decimal(str(payload["data"]["balance"]))
            if not amount.is_finite():
                raise ValueError("non-finite balance")
            return ProviderBalance(self.provider, self.display_name, "AVAILABLE", amount, "USD", "currency",
                                   True, now, now)
        except requests.Timeout:
            return self.unavailable(now, "TIMEOUT")
        except requests.RequestException:
            return self.unavailable(now, "PROVIDER_ERROR")
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return self.unavailable(now, "INVALID_RESPONSE")


class TwitterApiIoBalanceAdapter(BalanceAdapter):
    provider, display_name = "TWITTERAPI_IO", "TwitterAPI.io"
    endpoint = "https://api.twitterapi.io/oapi/my/info"

    def __init__(self, session=requests, api_key: str | None = None):
        self.session = session
        self.api_key = (api_key if api_key is not None else os.getenv("TWITTERAPI_API_KEY", "")).strip()

    def fetch(self, now: datetime) -> ProviderBalance:
        if not self.api_key:
            return ProviderBalance(self.provider, self.display_name, "CREDENTIAL_REQUIRED", checked_at=now,
                                   error_category="MISSING_CREDENTIAL")
        try:
            response = self.session.get(self.endpoint, headers={"X-API-Key": self.api_key}, timeout=(3.05, 8))
            if response.status_code in (401, 403):
                return ProviderBalance(self.provider, self.display_name, "CREDENTIAL_REQUIRED", checked_at=now,
                                       error_category="AUTHENTICATION")
            response.raise_for_status()
            payload = response.json()
            amount = Decimal(str(payload["recharge_credits"]))
            if not amount.is_finite():
                raise ValueError("non-finite balance")
            return ProviderBalance(self.provider, self.display_name, "AVAILABLE", amount, None, "credits",
                                   True, now, now)
        except requests.Timeout:
            return self.unavailable(now, "TIMEOUT")
        except requests.RequestException:
            return self.unavailable(now, "PROVIDER_ERROR")
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return self.unavailable(now, "INVALID_RESPONSE")


class XaiBalanceAdapter(BalanceAdapter):
    provider, display_name = "XAI", "xAI / Grok"
    base_url = "https://management-api.x.ai"

    def __init__(self, session=requests, api_key: str | None = None, team_id: str | None = None):
        self.session = session
        self.api_key = (api_key if api_key is not None else os.getenv("XAI_MANAGEMENT_API_KEY", "")).strip()
        self.team_id = (team_id if team_id is not None else os.getenv("XAI_TEAM_ID", "")).strip()

    def fetch(self, now: datetime) -> ProviderBalance:
        if not self.api_key or not self.team_id:
            return ProviderBalance(self.provider, self.display_name, "CREDENTIAL_REQUIRED", checked_at=now,
                                   error_category="MANAGEMENT_CREDENTIAL_REQUIRED")
        try:
            response = self.session.get(f"{self.base_url}/v1/billing/teams/{self.team_id}/prepaid/balance",
                                        headers={"Authorization": f"Bearer {self.api_key}"}, timeout=(3.05, 8))
            if response.status_code in (401, 403):
                return ProviderBalance(self.provider, self.display_name, "CREDENTIAL_REQUIRED", checked_at=now,
                                       error_category="AUTHENTICATION")
            response.raise_for_status()
            # xAI's billing ledger represents prepaid credits as a negative
            # liability (its official example reports a $10 purchase as -1000).
            # A remaining-credit balance is therefore the inverse ledger value.
            cents = Decimal(str(response.json()["total"]["val"]))
            if not cents.is_finite():
                raise ValueError("non-finite balance")
            return ProviderBalance(self.provider, self.display_name, "AVAILABLE", -cents / 100, "USD", "currency",
                                   True, now, now)
        except requests.Timeout:
            return self.unavailable(now, "TIMEOUT")
        except requests.RequestException:
            return self.unavailable(now, "PROVIDER_ERROR")
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return self.unavailable(now, "INVALID_RESPONSE")


class OpenAiBalanceAdapter(BalanceAdapter):
    provider, display_name = "OPENAI", "OpenAI"

    def fetch(self, now: datetime) -> ProviderBalance:
        return ProviderBalance(self.provider, self.display_name, "NOT_SUPPORTED", checked_at=now,
                               error_category="BALANCE_ENDPOINT_NOT_SUPPORTED")


class ApiBalanceService:
    """Process-local 60-minute cache with per-provider single-flight refreshes."""
    _cache: dict[str, ProviderBalance] = {}
    _locks: dict[str, threading.Lock] = {}
    _guard = threading.Lock()

    def __init__(self, adapters: list[BalanceAdapter] | None = None,
                 clock: Callable[[], datetime] | None = None, cache_minutes: int = 60):
        self.adapters = adapters or [WaveSpeedBalanceAdapter(), TwitterApiIoBalanceAdapter(), XaiBalanceAdapter(), OpenAiBalanceAdapter()]
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ttl = timedelta(minutes=cache_minutes)

    @classmethod
    def clear_cache(cls) -> None:
        with cls._guard:
            cls._cache.clear()

    def _lock(self, provider: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(provider, threading.Lock())

    def _get(self, adapter: BalanceAdapter, force: bool) -> ProviderBalance:
        now = self.clock()
        cached = self._cache.get(adapter.provider)
        observed = cached
        if not force and cached and cached.checked_at and now - cached.checked_at < self.ttl:
            return cached
        with self._lock(adapter.provider):
            now = self.clock()
            cached = self._cache.get(adapter.provider)
            if force and cached is not observed and cached is not None:
                return cached
            if not force and cached and cached.checked_at and now - cached.checked_at < self.ttl:
                return cached
            result = adapter.fetch(now)
            if result.status == "UNAVAILABLE" and cached and cached.authoritative:
                result = replace(cached, status="STALE", checked_at=now, error_category=result.error_category)
            self._cache[adapter.provider] = result
            return result

    def balances(self, *, force: bool = False) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=max(1, len(self.adapters))) as executor:
            results = list(executor.map(lambda adapter: self._get(adapter, force), self.adapters))
        checked = self.clock()
        return {"providers": [item.public_dict() for item in results], "checkedAt": checked.isoformat(),
                "cacheTtlSeconds": int(self.ttl.total_seconds())}
