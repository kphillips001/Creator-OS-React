"""Fail-closed validation for customer-facing commercial destinations."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CustomerFacingDestinationValidation:
    valid: bool
    scope: str
    origin: str | None
    failure_reason: str | None = None


def validate_customer_facing_commerce_url(
    value: str | None,
) -> CustomerFacingDestinationValidation:
    raw = str(value or "").strip()
    if not raw:
        return CustomerFacingDestinationValidation(
            False, "INVALID", None, "PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE"
        )
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").strip().lower().rstrip(".")
        port = parsed.port
    except (TypeError, ValueError):
        return CustomerFacingDestinationValidation(
            False, "INVALID", None, "CUSTOMER_FACING_DESTINATION_MALFORMED"
        )
    origin = (
        f"{parsed.scheme.lower()}://{host}"
        + (f":{port}" if port is not None else "")
        if parsed.scheme and host else None
    )
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        return CustomerFacingDestinationValidation(
            False, "INVALID", origin, "CUSTOMER_FACING_DESTINATION_INVALID_SCHEME"
        )
    if parsed.username or parsed.password:
        return CustomerFacingDestinationValidation(
            False, "INVALID", origin, "CUSTOMER_FACING_DESTINATION_HAS_CREDENTIALS"
        )
    if host == "localhost" or host.endswith(".localhost"):
        return CustomerFacingDestinationValidation(
            False, "LOCALHOST", origin, "CUSTOMER_FACING_DESTINATION_LOCALHOST"
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if address.is_loopback:
            scope = "LOCALHOST"
        elif (
            address.is_private or address.is_link_local or address.is_unspecified
            or address.is_reserved or address.is_multicast
        ):
            scope = "PRIVATE_NETWORK"
        else:
            scope = "PUBLIC"
        if scope != "PUBLIC":
            return CustomerFacingDestinationValidation(
                False, scope, origin,
                "CUSTOMER_FACING_DESTINATION_NOT_PUBLIC",
            )
    elif (
        "." not in host or host.endswith((".local", ".internal", ".lan", ".home"))
    ):
        return CustomerFacingDestinationValidation(
            False, "PRIVATE_NETWORK", origin,
            "CUSTOMER_FACING_DESTINATION_INTERNAL_HOSTNAME",
        )
    if parsed.scheme.lower() != "https":
        return CustomerFacingDestinationValidation(
            False, "PUBLIC", origin, "CUSTOMER_FACING_DESTINATION_HTTPS_REQUIRED"
        )
    return CustomerFacingDestinationValidation(True, "PUBLIC", origin)


def require_public_commerce_origin(value: str | None) -> str:
    result = validate_customer_facing_commerce_url(value)
    if not result.valid:
        from app.services.private_chat_unlock_gateway_service import (
            UnlockUnavailableError,
        )
        raise UnlockUnavailableError(result.failure_reason or "PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE")
    parsed = urlsplit(str(value).strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.rstrip('/')}"
