"""Explicit authorization boundary for temporary developer-only APIs."""
from __future__ import annotations

import hmac
import ipaddress
import os

from fastapi import Header, HTTPException, Request


def require_developer_authorization(
    request: Request,
    x_creator_os_developer_key: str | None = Header(default=None),
    x_creator_os_developer: str | None = Header(default=None),
) -> None:
    configured = os.getenv("CREATOR_OS_DEVELOPER_KEY", "").strip()
    supplied = str(x_creator_os_developer_key or "")
    if configured and hmac.compare_digest(configured, supplied):
        return
    hostname = (request.url.hostname or "").lower()
    peer = str(request.client.host if request.client else "").strip()
    try:
        peer_is_local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        peer_is_local = peer == "testclient" and hostname == "testserver"
    explicit_local = str(x_creator_os_developer or "").lower() == "true"
    if (
        not configured
        and explicit_local
        and peer_is_local
        and hostname in {"127.0.0.1", "localhost", "testserver", "::1"}
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="Explicit developer authorization is required.",
    )
