"""Narrow React adapter over the existing database-backed Fanvue OAuth flow."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.repositories.fanvue_account_repository import get_account_by_id
from app.services.fanvue_oauth_service import FanvueOAuthService

router = APIRouter(prefix="/api/v1/administration/providers", tags=["provider-connections"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTED_ACCOUNT_FILE = PROJECT_ROOT / "data/config/dashboard_selected_account.json"
OAUTH_SESSION_FILE = PROJECT_ROOT / "data/config/fanvue_react_oauth_session.json"
DEFAULT_REACT_CALLBACK_URI = (
    "http://localhost:8001/api/v1/administration/providers/fanvue/callback"
)
REQUIRED_MEDIA_LINK_SCOPES = frozenset(
    {"read:creator", "write:creator", "read:media", "write:media"}
)
FANVUE_API_VERSION = "2025-06-26"


def selected_account_id() -> int:
    try:
        body = json.loads(SELECTED_ACCOUNT_FILE.read_text(encoding="utf-8"))
        return int(body["last_selected_account_id"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Select a Fanvue dashboard account before authorizing.") from error


def _expiration(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _safe_status(account):
    granted = sorted(set(str(account.get("oauth_scope") or "").split()))
    missing = sorted(REQUIRED_MEDIA_LINK_SCOPES - set(granted))
    connected = bool(account.get("oauth_access_token"))
    worker_enabled = str(
        os.getenv("CREATOR_OS_LAUNCH_FANVUE_COMMERCIAL_PUBLICATIONS") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    return {
        "provider": "FANVUE",
        "connected": connected,
        "connectionStatus": (
            "REAUTHORIZATION_REQUIRED" if connected and missing
            else "CONNECTED" if connected else "NOT_CONNECTED"
        ),
        "account": {
            "id": int(account["id"]),
            "displayName": (
                account.get("display_name")
                or account.get("account_name")
                or account.get("username")
                or f"Account #{account['id']}"
            ),
            "username": account.get("username"),
            "fanvueUserUuid": account.get("fanvue_user_uuid"),
        },
        "grantedScopes": granted,
        "requiredScopes": sorted(REQUIRED_MEDIA_LINK_SCOPES),
        "missingScopes": missing,
        "accessTokenExpiresAt": _expiration(account.get("oauth_expires_at")),
        "refreshTokenAvailable": bool(account.get("oauth_refresh_token")),
        "lastSuccessfulRefresh": (
            account.get("updated_at").isoformat()
            if isinstance(account.get("updated_at"), datetime)
            else str(account.get("updated_at") or "") or None
        ),
        "connectedAt": (
            account.get("oauth_connected_at").isoformat()
            if isinstance(account.get("oauth_connected_at"), datetime)
            else str(account.get("oauth_connected_at") or "") or None
        ),
        "apiVersion": FANVUE_API_VERSION,
        "workerReady": worker_enabled,
        "publicationReady": connected and not missing,
        "mediaLinkCapability": {
            "ready": connected and not missing,
            "reason": None if connected and not missing else (
                "Missing " + ", ".join(missing) if missing else "Fanvue is not connected."
            ),
        },
    }


@router.get("/fanvue")
def fanvue_status():
    try:
        account_id = selected_account_id()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    account = get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Selected Fanvue account was not found.")
    return _safe_status(account)


@router.post("/fanvue/authorize")
def authorize_fanvue():
    try:
        account_id = selected_account_id()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    account = get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Selected Fanvue account was not found.")
    redirect_uri = (
        os.getenv("FANVUE_REACT_REDIRECT_URI") or DEFAULT_REACT_CALLBACK_URI
    ).strip()
    try:
        result = FanvueOAuthService(
            account_id,
            redirect_uri=redirect_uri,
        ).generate_authorization_url()
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    OAUTH_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    OAUTH_SESSION_FILE.write_text(json.dumps({
        "flow": "react_administration",
        "fanvue_account_id": account_id,
        "code_verifier": result["code_verifier"],
        "state": result["state"],
        "redirect_uri": redirect_uri,
    }), encoding="utf-8")
    return {"authorizationUrl": result["authorization_url"]}
