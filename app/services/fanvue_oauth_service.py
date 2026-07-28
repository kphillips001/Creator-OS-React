import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

from app.repositories.fanvue_account_repository import (
    load_oauth_tokens_for_account,
    save_oauth_tokens_for_account,
    update_oauth_tokens_for_account,
)

load_dotenv()


class FanvueOAuthService:
    def __init__(
        self,
        fanvue_account_id: int | None = None,
        redirect_uri: str | None = None,
    ):
        self.fanvue_account_id = fanvue_account_id
        self.client_id = os.getenv("FANVUE_CLIENT_ID")
        self.client_secret = os.getenv("FANVUE_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("FANVUE_REDIRECT_URI")
        self.auth_url = "https://auth.fanvue.com/oauth2/auth"
        self.token_url = "https://auth.fanvue.com/oauth2/token"

    def _base64url(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    def _validate_config(self):
        if not self.client_id:
            raise ValueError("Missing FANVUE_CLIENT_ID")
        if not self.client_secret:
            raise ValueError("Missing FANVUE_CLIENT_SECRET")
        if not self.redirect_uri:
            raise ValueError("Missing FANVUE_REDIRECT_URI")

    def _require_account_id(self):
        if not self.fanvue_account_id:
            raise ValueError("Missing fanvue_account_id for account-scoped OAuth tokens.")

    def _build_token_data(self, body: dict):
        expires_in = body.get("expires_in") or 3600

        return {
            "access_token": body.get("access_token"),
            "refresh_token": body.get("refresh_token"),
            "expires_in": expires_in,
            "expires_at": int(time.time()) + int(expires_in),
            "scope": body.get("scope"),
            "token_type": body.get("token_type"),
        }

    def generate_pkce_pair(self):
        code_verifier = self._base64url(secrets.token_bytes(32))
        code_challenge = self._base64url(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        )
        return code_verifier, code_challenge

    def generate_authorization_url(self):
        print("[FANVUE OAUTH URL START]")
        self._validate_config()

        code_verifier, code_challenge = self.generate_pkce_pair()
        state = secrets.token_hex(32)

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": (
                "openid offline_access offline "
                "read:self read:creator read:fan read:media "
                "write:creator write:media write:post read:chat write:chat read:insights"
            ),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        url = f"{self.auth_url}?{urlencode(params)}"

        print("[FANVUE OAUTH URL GENERATED]")
        return {
            "authorization_url": url,
            "code_verifier": code_verifier,
            "state": state,
        }

    def save_tokens(self, token_data: dict, fanvue_identity: dict | None = None):
        self._require_account_id()

        account = save_oauth_tokens_for_account(
            account_id=self.fanvue_account_id,
            token_data=token_data,
            fanvue_identity=fanvue_identity,
        )

        print("[FANVUE TOKENS SAVED TO DB]")
        print(f"fanvue_account_id={self.fanvue_account_id}")

        return account

    def load_tokens(self):
        self._require_account_id()

        tokens = load_oauth_tokens_for_account(self.fanvue_account_id)

        if not tokens:
            print("[FANVUE TOKENS MISSING FROM DB]")
            print(f"fanvue_account_id={self.fanvue_account_id}")
            return None

        return tokens

    def exchange_code_for_tokens(self, code: str, code_verifier: str):
        print("[FANVUE TOKEN EXCHANGE START]")
        self._validate_config()
        self._require_account_id()

        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }

        try:
            response = requests.post(
                self.token_url,
                data=data,
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )

            print(f"[FANVUE TOKEN RESPONSE] status={response.status_code}")

            try:
                body = response.json()
            except Exception:
                body = response.text

            if response.status_code >= 400:
                print("[FANVUE TOKEN EXCHANGE FAILED]")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": body,
                }

            print("[FANVUE TOKEN EXCHANGE SUCCESS]")

            token_data = self._build_token_data(body)
            self.save_tokens(token_data)

            return {
                "success": True,
                "status_code": response.status_code,
                **token_data,
            }

        except Exception as e:
            print(f"[FANVUE TOKEN EXCHANGE ERROR] {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
            }

    def refresh_access_token(self):
        print("[FANVUE TOKEN REFRESH START]")
        self._validate_config()
        self._require_account_id()

        existing_tokens = self.load_tokens()

        if not existing_tokens:
            return {
                "success": False,
                "reason": "missing_tokens",
            }

        refresh_token = existing_tokens.get("refresh_token")

        if not refresh_token:
            return {
                "success": False,
                "reason": "missing_refresh_token",
            }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        try:
            response = requests.post(
                self.token_url,
                data=data,
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )

            print(f"[FANVUE TOKEN REFRESH RESPONSE] status={response.status_code}")

            try:
                body = response.json()
            except Exception:
                body = response.text

            if response.status_code >= 400:
                print("[FANVUE TOKEN REFRESH FAILED]")
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": body,
                }

            print("[FANVUE TOKEN REFRESH SUCCESS]")

            token_data = self._build_token_data(body)

            if not token_data.get("refresh_token"):
                token_data["refresh_token"] = refresh_token

            update_oauth_tokens_for_account(
                account_id=self.fanvue_account_id,
                token_data=token_data,
            )

            return {
                "success": True,
                "status_code": response.status_code,
                **token_data,
            }

        except Exception as e:
            print(f"[FANVUE TOKEN REFRESH ERROR] {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
            }

    def get_valid_access_token(self):
        tokens = self.load_tokens()

        if not tokens:
            raise Exception("Fanvue tokens not found for selected account. Run OAuth flow first.")

        access_token = tokens.get("access_token")
        expires_at = tokens.get("expires_at")

        if not access_token:
            raise Exception("Fanvue access token missing for selected account. Run OAuth flow again.")

        if not expires_at:
            print("[FANVUE TOKEN EXPIRY UNKNOWN] Refreshing token")
            refresh_result = self.refresh_access_token()

            if not refresh_result.get("success"):
                raise Exception(f"Fanvue token refresh failed: {refresh_result}")

            return refresh_result.get("access_token")

        seconds_left = int(expires_at) - int(time.time())

        if seconds_left <= 300:
            print(f"[FANVUE TOKEN EXPIRING SOON] seconds_left={seconds_left}")

            refresh_result = self.refresh_access_token()

            if not refresh_result.get("success"):
                raise Exception(f"Fanvue token refresh failed: {refresh_result}")

            return refresh_result.get("access_token")

        print(f"[FANVUE TOKEN VALID] seconds_left={seconds_left}")

        return access_token

    def has_scopes(self, *required_scopes: str) -> bool:
        tokens = self.load_tokens() or {}
        granted = set(str(tokens.get("scope") or "").split())
        return set(required_scopes).issubset(granted)

    def require_scopes(self, *required_scopes: str) -> None:
        missing = [scope for scope in required_scopes if not self.has_scopes(scope)]
        if missing:
            raise FanvueReauthorizationRequired(
                "Fanvue reauthorization required for scopes: " + ", ".join(missing)
            )


class FanvueReauthorizationRequired(RuntimeError):
    pass
