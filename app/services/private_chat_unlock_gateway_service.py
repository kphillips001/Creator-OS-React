"""One-click private Telegram offer gateway and runtime Fanvue link lifecycle."""
from __future__ import annotations

import logging
import os
import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4
from psycopg.errors import UniqueViolation

from app.database import get_db_connection
from app.repositories.private_chat_fingerprint_repository import (
    PrivateChatFingerprintRepository,
    token_digest,
)
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.fanvue_official_client import FanvueOfficialClient
from app.services.fingerprint_price_allocator import FingerprintPricePolicy
from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService
from app.services.customer_facing_commerce_url_service import (
    require_public_commerce_origin,
    validate_customer_facing_commerce_url,
)


logger = logging.getLogger("private-chat-unlock")
UNLOCK_TOKEN_LENGTH = 64
UNLOCK_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{64}$")
PUBLIC_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")
PUBLIC_ALIAS_BYTES = 16
PUBLIC_ALIAS_COLLISION_ATTEMPTS = 5


def fingerprint_bootstrap_enabled() -> bool:
    return os.getenv(
        "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "false"
    ).strip().lower() == "true"


class UnlockUnavailableError(RuntimeError):
    pass


class PrivateChatUnlockGatewayService:
    BUTTON_LABEL = "🔓 Unlock"

    def __init__(
        self, *, repository=None, intent_repository=None, identities=None,
        client_factory=FanvueOfficialClient, connection_factory=get_db_connection,
        clock=lambda: datetime.now(timezone.utc), runtime_ttl=timedelta(hours=24),
        token_secret: str | None = None,
        controlled_autonomy_service=None, purchase_intent_lifecycle=None,
    ):
        self.repository = repository or PrivateChatFingerprintRepository()
        self.intents = intent_repository or PurchaseIntentRepository()
        self.identities = identities or TelegramIdentityRepository()
        self.client_factory = client_factory
        self.connection_factory = connection_factory
        self.clock = clock
        self.runtime_ttl = runtime_ttl
        self.prices = FingerprintPricePolicy()
        self.controlled_autonomy = (
            controlled_autonomy_service or ControlledAutonomyTestService()
        )
        self.token_secret = token_secret or os.getenv(
            "CREATOR_OS_UNLOCK_TOKEN_SECRET", ""
        )
        self.purchase_intent_lifecycle = purchase_intent_lifecycle

    def issue(self, intent):
        self._require_controlled_identity_when_enabled(intent)
        if len(self.token_secret.encode("utf-8")) < 32:
            raise UnlockUnavailableError(
                "CREATOR_OS_UNLOCK_TOKEN_SECRET must contain at least 32 bytes."
            )
        base = require_public_commerce_origin(
            os.getenv("CREATOR_OS_PUBLIC_API_URL")
        )
        existing = self.repository.get_grant_for_intent(intent.purchase_intent_id)
        grant_id = existing.unlock_grant_id if existing else UUID(
            bytes=secrets.token_bytes(16), version=4
        )
        token = self._token_for(grant_id)
        grant = self.repository.create_grant(
            grant_id=grant_id, token=token, intent=intent,
            audit_metadata={"provenance": "PRIVATE_CHAT_FINGERPRINT_PURCHASE"},
        )
        grant, alias = self._ensure_public_alias(grant)
        return grant, f"{base}/u/{quote(alias, safe='')}"

    def _token_for(self, grant_id):
        nonce = grant_id.bytes
        signature = hmac.new(
            self.token_secret.encode("utf-8"), nonce, hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(nonce + signature).rstrip(b"=").decode("ascii")

    def resolve(self, token: str) -> str:
        return self._validated_fanvue_destination(self._resolve_destination(token))

    def resolve_alias(self, alias: str) -> str:
        if not fingerprint_bootstrap_enabled():
            raise UnlockUnavailableError("Private-chat fingerprint bootstrap is disabled.")
        if not alias or PUBLIC_ALIAS_PATTERN.fullmatch(alias) is None:
            raise UnlockUnavailableError("Unlock alias is invalid.")
        grant = self.repository.resolve_grant_by_alias(alias)
        if grant is None:
            raise UnlockUnavailableError("Unlock alias is unavailable or revoked.")
        return self._validated_fanvue_destination(
            self._resolve_claimed_grant(grant)
        )

    def _resolve_destination(self, token: str) -> str:
        if not fingerprint_bootstrap_enabled():
            raise UnlockUnavailableError("Private-chat fingerprint bootstrap is disabled.")
        if not token or UNLOCK_TOKEN_PATTERN.fullmatch(token) is None:
            raise UnlockUnavailableError("Unlock token is invalid.")
        grant = self.repository.resolve_grant(token)
        if grant is None:
            raise UnlockUnavailableError("Unlock token is unavailable or revoked.")
        return self._resolve_claimed_grant(grant)

    def _resolve_claimed_grant(self, grant) -> str:
        intent = self.intents.get(grant.purchase_intent_id)
        if intent is None or not self._bindings_match(grant, intent):
            raise UnlockUnavailableError("Unlock grant integrity check failed.")
        self._require_controlled_identity_when_enabled(intent)
        publication = self._eligible_publication(intent)
        self._record_valid_click(intent, clicked_at=grant.last_used_at)
        mapping = self.identities.get_verified_by_telegram_user_id(
            intent.telegram_user_id
        )
        if mapping is not None:
            return str(publication["delivery_url"])

        with self.repository.serialize_intent(intent.purchase_intent_id):
            now = self.clock()
            active = self.repository.get_live_link(intent.purchase_intent_id, now=now)
            if active is not None and active.provider_url:
                return active.provider_url
            self.repository.retire_expired_for_intent(intent.purchase_intent_id, now=now)

            canonical_prices = self._canonical_prices(
                intent.fanvue_account_id, intent.expected_currency
            )
            reservation = self.repository.reserve_price(
                intent=intent,
                canonical_prices=canonical_prices,
                candidate_prices=tuple(self.prices.candidates(intent.expected_price_minor)),
            )
            runtime = self.repository.prepare_runtime_link(
                intent=intent, reservation=reservation,
                expires_at=now + self.runtime_ttl,
            )
            claimed = self.repository.mark_creating(runtime.runtime_media_link_id)
            if claimed is None:
                recovered = self.repository.get_live_link(intent.purchase_intent_id, now=now)
                if recovered is not None and recovered.provider_url:
                    return recovered.provider_url
                raise UnlockUnavailableError("Unlock resource is being prepared; retry safely.")
            media_uuids = tuple(publication["media_uuids"])
            if not media_uuids:
                raise UnlockUnavailableError("Offering has no authoritative Fanvue media.")
            try:
                client = self.client_factory(intent.fanvue_account_id)
                matches = client.find_equivalent_media_link(
                    media_uuids, reservation.exact_price_minor
                )
                if len(matches) > 1:
                    raise UnlockUnavailableError(
                        "Multiple provider resources match the reserved fingerprint."
                    )
                link = matches[0] if matches else client.create_media_link(
                    media_uuids, reservation.exact_price_minor
                )
                provider_uuid = str(link.get("uuid") or "").strip()
                provider_url = str(link.get("url") or "").strip()
                if not provider_uuid or not provider_url:
                    raise UnlockUnavailableError("Fanvue returned an incomplete Media Link.")
                active = self.repository.activate(
                    runtime.runtime_media_link_id,
                    provider_uuid=provider_uuid, provider_url=provider_url,
                )
                self.intents.update(
                    intent.purchase_intent_id,
                    identity_bootstrap_mode="PRIVATE_CHAT_FINGERPRINT",
                )
                return active.provider_url
            except Exception as error:
                self.repository.mark_creation_uncertain(runtime.runtime_media_link_id, error)
                logger.error(
                    "event=runtime_media_link_creation_uncertain intent_id=%s error_type=%s",
                    intent.purchase_intent_id, type(error).__name__,
                )
                raise UnlockUnavailableError(
                    "Fanvue Unlock preparation is uncertain and requires safe recovery."
                ) from error

    def _ensure_public_alias(self, grant):
        generation = grant.public_alias_generation
        if grant.public_alias_hash and generation is not None:
            alias = self._public_alias_for(grant.unlock_grant_id, generation)
            if token_digest(alias) != grant.public_alias_hash:
                raise UnlockUnavailableError("Unlock alias integrity check failed.")
            return grant, alias
        for generation in range(PUBLIC_ALIAS_COLLISION_ATTEMPTS):
            alias = self._public_alias_for(grant.unlock_grant_id, generation)
            try:
                assigned = self.repository.assign_public_alias(
                    grant_id=grant.unlock_grant_id,
                    alias_hash=token_digest(alias), generation=generation,
                )
            except UniqueViolation:
                continue
            if assigned is not None:
                return assigned, alias
            current = self.repository.get_grant_for_intent(
                grant.purchase_intent_id
            )
            if current and current.public_alias_hash:
                return self._ensure_public_alias(current)
        raise UnlockUnavailableError("Unlock alias uniqueness could not be established.")

    def _public_alias_for(self, grant_id, generation: int) -> str:
        if len(self.token_secret.encode("utf-8")) < 32:
            raise UnlockUnavailableError(
                "CREATOR_OS_UNLOCK_TOKEN_SECRET must contain at least 32 bytes."
            )
        material = (
            b"creator-os:unlock-public-alias:v1\0"
            + grant_id.bytes
            + int(generation).to_bytes(2, "big")
        )
        digest = hmac.new(
            self.token_secret.encode("utf-8"), material, hashlib.sha256
        ).digest()[:PUBLIC_ALIAS_BYTES]
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def reconcile_persisted_click(self, intent_id, *, unlock_grant_id):
        """Record a missed click only from complete, consistent durable evidence."""
        intent = self.intents.get(intent_id)
        grant = self.repository.get_grant_for_intent(intent_id)
        reservation = self.repository.get_reservation_for_intent(intent_id)
        runtime = self.repository.get_runtime_link_for_intent(intent_id)
        if intent is None or grant is None or reservation is None or runtime is None:
            raise ValueError("Persisted Unlock click evidence is incomplete.")
        if (
            grant.unlock_grant_id != unlock_grant_id
            or grant.purchase_intent_id != intent.purchase_intent_id
            or grant.state != "ACTIVE"
            or int(grant.use_count) < 1
            or grant.last_used_at is None
            or reservation.purchase_intent_id != intent.purchase_intent_id
            or runtime.purchase_intent_id != intent.purchase_intent_id
            or runtime.fingerprint_reservation_id
            != reservation.fingerprint_reservation_id
            or str(reservation.state) not in {"ACTIVE", "FingerprintReservationState.ACTIVE"}
            or str(runtime.state) not in {"ACTIVE", "RuntimeMediaLinkState.ACTIVE"}
        ):
            raise ValueError("Persisted Unlock click evidence is contradictory.")
        if (
            intent.purchased_at is not None
            or intent.provider_transaction_order_id is not None
            or intent.provider_payment_id is not None
            or intent.provider_event_id is not None
        ):
            raise ValueError("Purchase evidence blocks Unlock click reconciliation.")
        return self._record_valid_click(intent, clicked_at=grant.last_used_at)

    def _record_valid_click(self, intent, *, clicked_at):
        if self.purchase_intent_lifecycle is None:
            from app.services.purchase_intent_service import PurchaseIntentService
            self.purchase_intent_lifecycle = PurchaseIntentService(
                repository=self.intents,
            )
        return self.purchase_intent_lifecycle.record_click(
            intent.purchase_intent_id, clicked_at=clicked_at,
        )

    @staticmethod
    def _validated_fanvue_destination(destination: str | None) -> str:
        value = str(destination or "").strip()
        validation = validate_customer_facing_commerce_url(value)
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except (TypeError, ValueError):
            parsed = None
            port = None
        configured = os.getenv(
            "TELEGRAM_ALLOWED_FANVUE_HOSTNAMES", "fanvue.com,www.fanvue.com"
        )
        allowed_hosts = {
            item.strip().lower().rstrip(".")
            for item in configured.split(",")
            if item.strip()
        }
        hostname = (parsed.hostname or "").lower().rstrip(".") if parsed else ""
        if (
            not validation.valid
            or parsed is None
            or parsed.scheme.lower() != "https"
            or hostname not in allowed_hosts
            or port not in (None, 443)
        ):
            raise UnlockUnavailableError("Unlock destination failed security validation.")
        return value

    @staticmethod
    def _bindings_match(grant, intent) -> bool:
        return all((
            grant.telegram_user_id == intent.telegram_user_id,
            grant.telegram_chat_id == intent.telegram_chat_id,
            grant.commercial_offering_id == intent.commercial_offering_id,
            grant.commercial_publication_id == intent.commercial_publication_id,
            grant.fanvue_account_id == intent.fanvue_account_id,
            grant.currency == intent.expected_currency,
        ))

    def _require_controlled_identity_when_enabled(self, intent) -> None:
        if os.getenv(
            ControlledAutonomyTestService.ENABLED_ENV, "false"
        ).strip().lower() != "true":
            return
        decision = self.controlled_autonomy.decide(
            telegram_user_id=intent.telegram_user_id,
            telegram_chat_id=intent.telegram_chat_id,
        )
        if not decision.allowed:
            raise UnlockUnavailableError(
                "Private-chat Unlock is outside the controlled test boundary."
            )

    def _eligible_publication(self, intent):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT publication.publication_metadata,
                              offering.status AS offering_status,
                              publication.status AS publication_status
                       FROM public.commercial_offerings offering
                       JOIN public.commercial_publications publication
                         ON publication.publication_id=%s
                        AND publication.commercial_offering_id=offering.offering_id
                       WHERE offering.offering_id=%s
                         AND offering.creator_profile_id=%s""",
                    (intent.commercial_publication_id, intent.commercial_offering_id,
                     intent.creator_profile_id),
                )
                row = cursor.fetchone()
        if row is None or row["offering_status"] != "READY" or row["publication_status"] != "LIVE":
            raise UnlockUnavailableError("Offering is no longer eligible.")
        metadata = row.get("publication_metadata") or {}
        media = metadata.get("media_link") or {}
        return {
            "delivery_url": media.get("url"),
            "media_uuids": tuple(media.get("media_uuids") or ()),
        }

    def _canonical_prices(self, account_id: int, currency: str):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT offering.price_minor
                       FROM public.commercial_offerings offering
                       JOIN public.commercial_publications publication
                         ON publication.commercial_offering_id=offering.offering_id
                       JOIN public.purchase_intents intent
                         ON intent.commercial_publication_id=publication.publication_id
                       WHERE intent.fanvue_account_id=%s
                         AND offering.currency=%s
                         AND offering.status='READY' AND publication.status='LIVE'""",
                    (account_id, currency),
                )
                return {int(row["price_minor"]) for row in cursor.fetchall()}
