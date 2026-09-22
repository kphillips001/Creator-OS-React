from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Thread
from time import sleep

from fastapi.testclient import TestClient

from app.fanvue_callback_server import app
from app.services.api_balance_service import (
    ApiBalanceService, BalanceAdapter, OpenAiBalanceAdapter, ProviderBalance,
    TwitterApiIoBalanceAdapter, WaveSpeedBalanceAdapter, XaiBalanceAdapter,
)


NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


class Response:
    def __init__(self, body, status=200): self.body, self.status_code = body, status
    def json(self): return self.body
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError()


class Session:
    def __init__(self, response): self.response, self.calls = response, []
    def get(self, *args, **kwargs): self.calls.append((args, kwargs)); return self.response


def test_provider_adapters_parse_authoritative_units_and_never_expose_credentials():
    wave_session = Session(Response({"data": {"balance": 50.25}}))
    wave = WaveSpeedBalanceAdapter(wave_session, "secret").fetch(NOW)
    twitter_session = Session(Response({"recharge_credits": 123}))
    twitter = TwitterApiIoBalanceAdapter(twitter_session, "secret").fetch(NOW)
    xai_session = Session(Response({"total": {"val": "-725"}}))
    xai = XaiBalanceAdapter(xai_session, "secret", "team").fetch(NOW)
    assert (wave.balance, wave.currency, wave.unit, wave.authoritative) == (Decimal("50.25"), "USD", "currency", True)
    assert (twitter.balance, twitter.unit) == (Decimal("123"), "credits")
    assert (xai.balance, xai.currency) == (Decimal("7.25"), "USD")
    assert "secret" not in str(wave.public_dict()) + str(twitter.public_dict()) + str(xai.public_dict())
    assert wave_session.calls[0][0][0].endswith("/api/v3/balance")
    assert twitter_session.calls[0][0][0].endswith("/oapi/my/info")


def test_missing_credentials_and_openai_are_honest():
    assert WaveSpeedBalanceAdapter(api_key="").fetch(NOW).status == "CREDENTIAL_REQUIRED"
    assert TwitterApiIoBalanceAdapter(api_key="").fetch(NOW).status == "CREDENTIAL_REQUIRED"
    assert XaiBalanceAdapter(api_key="", team_id="").fetch(NOW).error_category == "MANAGEMENT_CREDENTIAL_REQUIRED"
    openai = OpenAiBalanceAdapter().fetch(NOW)
    assert openai.status == "NOT_SUPPORTED" and openai.balance is None and not openai.authoritative
    assert "last_successful_at" not in openai.public_dict()


class Adapter(BalanceAdapter):
    provider, display_name = "TEST", "Test"
    def __init__(self): self.calls = 0; self.fail = False
    def fetch(self, now):
        self.calls += 1; sleep(.01)
        if self.fail: return self.unavailable(now, "TIMEOUT")
        return ProviderBalance(self.provider, self.display_name, "AVAILABLE", Decimal("9"), "USD", "currency", True, now, now)


def test_cache_refresh_stale_fallback_and_single_flight():
    ApiBalanceService.clear_cache(); adapter = Adapter(); current = [NOW]
    service = ApiBalanceService([adapter], clock=lambda: current[0])
    assert service.balances()["providers"][0]["balance"] == "9"
    service.balances(); assert adapter.calls == 1
    current[0] += timedelta(minutes=61); adapter.fail = True
    stale = service.balances()["providers"][0]
    assert stale["status"] == "STALE" and stale["balance"] == "9" and stale["errorCategory"] == "TIMEOUT"
    ApiBalanceService.clear_cache(); adapter.fail = False; adapter.calls = 0
    threads = [Thread(target=service.balances) for _ in range(5)]
    [thread.start() for thread in threads]; [thread.join() for thread in threads]
    assert adapter.calls == 1


def test_authenticated_api_contract(monkeypatch):
    adapter = Adapter(); ApiBalanceService.clear_cache()
    monkeypatch.setattr("app.api.api_balances.ApiBalanceService", lambda: ApiBalanceService([adapter], clock=lambda: NOW))
    client = TestClient(app)
    denied = client.get("/api/v1/business/api-balances")
    assert denied.status_code == 403
    response = client.get("/api/v1/business/api-balances", headers={"X-Creator-OS-Developer": "true"})
    assert response.status_code == 200
    assert set(response.json()["providers"][0]) == {"provider", "displayName", "status", "balance", "currency", "unit", "authoritative", "checkedAt", "lastSuccessfulAt", "errorCategory"}
