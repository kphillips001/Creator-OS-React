"""Documented, versioned Fanvue operations used by publication execution."""
from __future__ import annotations
import time
from typing import Any
import requests

from app.services.fanvue_oauth_service import (
    FanvueOAuthService, FanvueReauthorizationRequired,
)

class FanvueAPIError(RuntimeError):
    def __init__(self, message, *, status_code=None, body=None, retry_after=None):
        super().__init__(message)
        self.status_code, self.body, self.retry_after = status_code, body, retry_after

class FanvueOfficialClient:
    API_VERSION = "2025-06-26"
    BASE_URL = "https://api.fanvue.com"

    def __init__(self, fanvue_account_id: int, *, oauth=None, session=None, sleep=time.sleep):
        self.oauth = oauth or FanvueOAuthService(fanvue_account_id)
        self.session = session or requests
        self.sleep = sleep

    def require_media_link_scopes(self):
        self.oauth.require_scopes("read:creator", "write:creator", "read:media", "write:media")

    def _headers(self, token, json_content=True):
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Fanvue-API-Version": self.API_VERSION,
        }
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _body(response):
        try:
            return response.json()
        except Exception:
            return response.text

    def request(self, method, path, *, retry_429=True, **kwargs):
        token = self.oauth.get_valid_access_token()
        for attempt in range(2):
            response = self.session.request(
                method, f"{self.BASE_URL}{path}",
                headers=self._headers(token), timeout=kwargs.pop("timeout", 30), **kwargs,
            )
            if response.status_code == 401 and attempt == 0:
                refresh = self.oauth.refresh_access_token()
                if not refresh.get("success"):
                    body = refresh.get("response") or {}
                    if "invalid_grant" in str(body):
                        raise FanvueReauthorizationRequired("Fanvue reauthorization required.")
                    raise FanvueAPIError("Fanvue token refresh failed.", status_code=401)
                token = refresh["access_token"]
                continue
            if response.status_code == 429 and retry_429 and attempt == 0:
                delay = max(0, int(response.headers.get("Retry-After", "1")))
                self.sleep(delay)
                continue
            if response.status_code >= 400:
                raise FanvueAPIError(
                    f"Fanvue request failed with HTTP {response.status_code}.",
                    status_code=response.status_code, body=self._body(response),
                    retry_after=response.headers.get("Retry-After"),
                )
            return response
        raise FanvueAPIError("Fanvue request retry exhausted.")

    def create_upload_session(self, *, name, filename, media_type, size_bytes):
        return self._body(self.request("POST", "/media/uploads", json={
            "name": name, "filename": filename, "mediaType": media_type,
            "sizeBytes": size_bytes,
        }))

    def get_upload_part_url(self, upload_id, part_number):
        return self.request("GET", f"/media/uploads/{upload_id}/parts/{part_number}/url").text.strip()

    def put_part(self, signed_url, content):
        response = self.session.put(signed_url, data=content, timeout=120)
        if response.status_code >= 400:
            raise FanvueAPIError("Fanvue signed upload part failed.", status_code=response.status_code)
        return response.headers.get("ETag") or ""

    def complete_upload(self, upload_id, parts):
        return self._body(self.request("PATCH", f"/media/uploads/{upload_id}", json={"parts": parts}))

    def get_media(self, media_uuid):
        return self._body(self.request("GET", f"/media/{media_uuid}"))

    def get_current_user(self):
        return self._body(self.request("GET", "/users/me"))

    def get_earnings_by_transaction(self, transaction_order_id):
        transaction_id = str(transaction_order_id or "").strip()
        if not transaction_id:
            raise ValueError("transaction_order_id is required.")
        return self._body(self.request(
            "GET", "/insights/earnings",
            params={"transactionOrderIds": transaction_id},
        ))

    def create_media_link(self, media_uuids, price_minor):
        self.require_media_link_scopes()
        if not 300 <= int(price_minor) <= 50000:
            raise ValueError("Fanvue Media Link price must be between 300 and 50000 minor units.")
        return self._body(self.request("POST", "/media-links", json={
            "mediaUuids": list(media_uuids), "price": int(price_minor),
        }))

    def list_media_links(self):
        self.require_media_link_scopes()
        return self._body(self.request("GET", "/media-links"))

    def delete_media_link(self, uuid):
        self.require_media_link_scopes()
        self.request("DELETE", f"/media-links/{uuid}")

    def find_equivalent_media_link(self, media_uuids, price_minor):
        expected = tuple(sorted(media_uuids))
        data = self.list_media_links().get("data", [])
        return [item for item in data if int(item.get("price", -1)) == int(price_minor)
                and tuple(sorted(item.get("mediaUuids") or [])) == expected]
