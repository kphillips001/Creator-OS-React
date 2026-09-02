import pytest

from app.services.customer_facing_commerce_url_service import (
    validate_customer_facing_commerce_url,
)


def test_public_https_commerce_origin_is_valid():
    result = validate_customer_facing_commerce_url(
        "https://commerce.creator.example/api/v1/commerce/unlock/token"
    )
    assert result.valid is True
    assert result.scope == "PUBLIC"
    assert result.origin == "https://commerce.creator.example"


@pytest.mark.parametrize("url,scope", [
    ("http://localhost:8001/unlock/x", "LOCALHOST"),
    ("http://127.0.0.1:8001/unlock/x", "LOCALHOST"),
    ("http://127.22.4.9/unlock/x", "LOCALHOST"),
    ("http://[::1]/unlock/x", "LOCALHOST"),
    ("http://0.0.0.0/unlock/x", "PRIVATE_NETWORK"),
    ("http://10.0.0.2/unlock/x", "PRIVATE_NETWORK"),
    ("http://172.16.1.2/unlock/x", "PRIVATE_NETWORK"),
    ("http://192.168.1.2/unlock/x", "PRIVATE_NETWORK"),
    ("http://169.254.1.2/unlock/x", "PRIVATE_NETWORK"),
    ("https://creator.internal/unlock/x", "PRIVATE_NETWORK"),
])
def test_internal_commerce_destinations_are_rejected(url, scope):
    result = validate_customer_facing_commerce_url(url)
    assert result.valid is False
    assert result.scope == scope


@pytest.mark.parametrize("url", [None, "", "not a url", "ftp://creator.example/x"])
def test_missing_or_malformed_destination_is_rejected(url):
    assert validate_customer_facing_commerce_url(url).valid is False


def test_public_http_requires_https():
    result = validate_customer_facing_commerce_url("http://creator.example/unlock/x")
    assert result.valid is False
    assert result.scope == "PUBLIC"
    assert result.failure_reason == "CUSTOMER_FACING_DESTINATION_HTTPS_REQUIRED"
