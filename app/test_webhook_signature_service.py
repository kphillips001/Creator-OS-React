import hashlib
import hmac
from pathlib import Path

from app.services.webhook_signature_service import WebhookSignatureService


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "fanvue_webhooks"
    / "purchase_new.json"
)
FIXTURE_SECRET = "whsec_fixture_only_not_a_provider_credential"
FIXTURE_TIMESTAMP = 1784937498


def _captured_purchase_body() -> bytes:
    return FIXTURE_PATH.read_bytes()


def _signature(body: bytes, timestamp: int = FIXTURE_TIMESTAMP) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + body
    digest = hmac.new(
        FIXTURE_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v0={digest}"


def _service(
    *,
    secret: str = FIXTURE_SECRET,
    now: int = FIXTURE_TIMESTAMP,
) -> WebhookSignatureService:
    return WebhookSignatureService(
        secret,
        clock=lambda: now,
    )


def test_captured_purchase_new_payload_validates_with_fanvue_algorithm():
    body = _captured_purchase_body()

    assert _service().verify_signature(body, _signature(body)) is True


def test_payload_must_remain_the_exact_captured_bytes():
    body = _captured_purchase_body()
    reformatted_body = body.replace(b'","', b'", "')

    assert _service().verify_signature(reformatted_body, _signature(body)) is False


def test_wrong_signing_secret_is_rejected():
    body = _captured_purchase_body()

    assert _service(secret="wrong-secret").verify_signature(
        body,
        _signature(body),
    ) is False


def test_missing_or_malformed_signature_is_rejected():
    body = _captured_purchase_body()

    assert _service().verify_signature(body, None) is False
    assert _service().verify_signature(body, "v0=abc") is False
    assert _service().verify_signature(body, "t=1784937498") is False


def test_stale_signature_is_rejected():
    body = _captured_purchase_body()

    assert _service(now=FIXTURE_TIMESTAMP + 301).verify_signature(
        body,
        _signature(body),
    ) is False


def test_any_v0_signature_may_match_during_secret_rotation():
    body = _captured_purchase_body()
    valid_header = _signature(body)
    header = f"{valid_header},v0={'0' * 64}"

    assert _service().verify_signature(body, header) is True
