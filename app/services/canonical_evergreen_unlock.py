"""Canonical adapters for the existing evergreen lifecycle; disabled by default.

The immutable family references existing intents/reservations. It is not another
order or fulfillment store. Only explicit checkout actions invoke this adapter.
"""

import json
import os
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid5, NAMESPACE_URL

from app.models.evergreen_checkout import (
    CheckoutBinding,
    CheckoutGrant,
    CheckoutTransaction,
    CheckoutPrice,
    CheckoutEligibility,
    CheckoutUnavailable,
)
from app.repositories.private_chat_fingerprint_repository import token_digest
from app.repositories.purchase_intent_repository import (
    PurchaseIntentRepository,
    purchase_intent_advisory_lock_key,
)
from app.repositories.evergreen_checkout_repository import EvergreenCheckoutRepository
from app.services.evergreen_checkout_service import EvergreenCheckoutService

NAMESPACE = "creator-os-private-unlock"
BINDING_FIELDS = (
    "creator_profile_id",
    "fanvue_account_id",
    "telegram_user_id",
    "telegram_chat_id",
    "commercial_offering_id",
    "commercial_publication_id",
    "provider",
    "provider_resource_id",
)


def enabled():
    return os.getenv("EVERGREEN_UNLOCK_ENABLED", "false").lower() == "true"


def binding(row):
    return CheckoutBinding(
        str(row["creator_profile_id"]) + ":" + str(row["fanvue_account_id"]),
        str(row["telegram_user_id"]),
        str(row["commercial_offering_id"]),
        str(row["telegram_chat_id"]),
    )


def snapshot(row):
    return {k: str(row[k]) for k in BINDING_FIELDS}


class CanonicalUnlockAuthority:
    def __init__(self, gateway, alias):
        self.gateway, self.alias = gateway, alias
        self.family = None

    def authenticate(self, alias, expected, *, connection):
        row = connection.execute(
            """SELECT i.*,g.unlock_grant_id,g.state AS grant_state,
            g.telegram_user_id AS grant_user,g.telegram_chat_id AS grant_chat,
            g.fanvue_account_id AS grant_account,g.commercial_offering_id AS grant_offer,
            g.commercial_publication_id AS grant_publication,g.currency AS grant_currency
            FROM telegram_unlock_grants g JOIN purchase_intents i USING(purchase_intent_id)
            WHERE g.public_alias_hash=%s""",
            (token_digest(alias),),
        ).fetchone()
        if not row or binding(row) != expected:
            raise CheckoutUnavailable("IDENTITY_MISMATCH")
        if (
            row["grant_user"],
            row["grant_chat"],
            row["grant_account"],
            row["grant_offer"],
            row["grant_publication"],
            row["grant_currency"],
        ) != (
            row["telegram_user_id"],
            row["telegram_chat_id"],
            row["fanvue_account_id"],
            row["commercial_offering_id"],
            row["commercial_publication_id"],
            row["expected_currency"],
        ):
            raise CheckoutUnavailable("GRANT_BINDING_MISMATCH")
        return CheckoutGrant(
            row["unlock_grant_id"],
            row["purchase_intent_id"],
            expected,
            row["grant_state"] != "ACTIVE",
        )

    def lock_scope(self, grant, *, connection):
        row = connection.execute(
            "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s",
            (grant.original_transaction_id,),
        ).fetchone()
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s::bigint)",
            (
                purchase_intent_advisory_lock_key(
                    fanvue_account_id=row["fanvue_account_id"],
                    telegram_user_id=row["telegram_user_id"],
                ),
            ),
        )
        # Family serialization precedes local authority locks. Settlement uses the
        # same buyer key before locking reservation/intent evidence.
        connection.execute(
            "SELECT 1 FROM telegram_unlock_grants WHERE unlock_grant_id=%s FOR UPDATE",
            (grant.alias_id,),
        )
        existing = connection.execute(
            "SELECT * FROM evergreen_offer_authorities WHERE original_intent_id=%s",
            (grant.original_transaction_id,),
        ).fetchone()
        if existing:
            self.family = existing
            return
        publication = self.publication(connection, row)
        reservation = connection.execute(
            "SELECT * FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s",
            (grant.original_transaction_id,),
        ).fetchone()
        if reservation and reservation["state"] not in (
            "RESERVED",
            "ACTIVE",
            "RETIRED",
        ):
            raise CheckoutUnavailable("FINGERPRINT_UNAVAILABLE")
        if (
            not reservation
            and row["identity_bootstrap_mode"] == "PRIVATE_CHAT_FINGERPRINT"
        ):
            raise CheckoutUnavailable("PRICE_EVIDENCE_MISSING")
        base = (
            row["configured_base_price_minor"]
            if row["configured_base_price_minor"] is not None
            else row["expected_price_minor"]
        )
        if (
            int(base) != int(publication["price_minor"])
            or row["expected_currency"] != publication["currency"]
        ):
            raise CheckoutUnavailable("PRICE_AUTHORITY_CHANGED")
        final = (
            reservation["exact_price_minor"]
            if reservation
            else row["expected_price_minor"]
        )
        if reservation and (
            reservation["currency"] != row["expected_currency"]
            or reservation["configured_base_price_minor"] != base
        ):
            raise CheckoutUnavailable("PRICE_EVIDENCE_MISMATCH")
        media = (publication["publication_metadata"].get("media_link") or {}).get(
            "media_uuids"
        ) or []
        if not media:
            raise CheckoutUnavailable("PRODUCT_IDENTITY_MISSING")
        connection.execute(
            """INSERT INTO evergreen_offer_authorities
            (original_intent_id,unlock_grant_id,fingerprint_reservation_id,configured_price_minor,
             final_price_minor,currency,binding,media_uuids) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
            (
                grant.original_transaction_id,
                grant.alias_id,
                reservation["fingerprint_reservation_id"] if reservation else None,
                base,
                final,
                row["expected_currency"],
                json.dumps(snapshot(row)),
                json.dumps(sorted(media)),
            ),
        )
        self.family = connection.execute(
            "SELECT * FROM evergreen_offer_authorities WHERE original_intent_id=%s",
            (grant.original_transaction_id,),
        ).fetchone()

    @staticmethod
    def publication(c, row):
        p = c.execute(
            """SELECT o.status AS offering_status,o.price_minor,o.currency,p.status AS publication_status,
            p.publication_metadata,p.external_product_id,p.provider_resource_status FROM commercial_offerings o JOIN commercial_publications p
            ON p.commercial_offering_id=o.offering_id WHERE o.offering_id=%s AND p.publication_id=%s
            AND o.creator_profile_id=%s AND p.provider=%s FOR SHARE OF o,p""",
            (
                row["commercial_offering_id"],
                row["commercial_publication_id"],
                row["creator_profile_id"],
                row["provider"],
            ),
        ).fetchone()
        if (
            not p
            or p["offering_status"] != "READY"
            or p["publication_status"] != "LIVE"
        ):
            raise CheckoutUnavailable("PRODUCT_UNAVAILABLE")
        if not p["external_product_id"] or p["provider_resource_status"] in (
            "MISSING",
            "MISMATCH",
            "AMBIGUOUS",
        ):
            raise CheckoutUnavailable("PRODUCT_IDENTITY_CHANGED")
        members = c.execute(
            "SELECT a.* FROM content_items a JOIN commercial_offering_assets m ON m.asset_id=a.id WHERE m.offering_id=%s FOR SHARE OF a,m",
            (row["commercial_offering_id"],),
        ).fetchall()
        if not members:
            raise CheckoutUnavailable("PRODUCT_UNAVAILABLE")
        from app.services.reference_asset_protection import (
            require_commercially_eligible_asset,
        )
        from types import SimpleNamespace

        for asset in members:
            if asset["creator_profile_id"] != row["creator_profile_id"]:
                raise CheckoutUnavailable("PRODUCT_IDENTITY_CHANGED")
            try:
                require_commercially_eligible_asset(SimpleNamespace(**asset))
            except ValueError as error:
                raise CheckoutUnavailable("PRODUCT_UNAVAILABLE") from error
        return p

    def load(self, transaction_id, *, connection):
        row = connection.execute(
            "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s FOR UPDATE",
            (transaction_id,),
        ).fetchone()
        if not row:
            return None
        f = self.family
        if snapshot(row) != f["binding"]:
            raise CheckoutUnavailable("BINDING_CHANGED")
        return CheckoutTransaction(
            transaction_id,
            binding(row),
            str(row["commercial_offering_id"]),
            row["status"],
            row["expires_at"],
            CheckoutPrice(f["final_price_minor"], f["currency"]),
        )

    def validate(self, grant, transaction, *, connection):
        c = connection
        f = self.family
        row = c.execute(
            "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s",
            (transaction.transaction_id,),
        ).fetchone()
        self.gateway._require_controlled_identity_when_enabled(
            PurchaseIntentRepository._intent(row)
        )
        account = c.execute(
            "SELECT is_active FROM fanvue_accounts WHERE id=%s FOR SHARE",
            (row["fanvue_account_id"],),
        ).fetchone()
        creator = c.execute(
            "SELECT is_active FROM creator_profiles WHERE id=%s FOR SHARE",
            (row["creator_profile_id"],),
        ).fetchone()
        if (
            not account
            or not creator
            or account["is_active"] is not True
            or creator["is_active"] is not True
        ):
            raise CheckoutUnavailable("COMMERCE_BLOCKED")

        p = self.publication(c, row)
        if (
            p["price_minor"] != f["configured_price_minor"]
            or p["currency"] != f["currency"]
        ):
            raise CheckoutUnavailable("PRICE_AUTHORITY_CHANGED")
        if (
            sorted(
                (p["publication_metadata"].get("media_link") or {}).get("media_uuids")
                or []
            )
            != f["media_uuids"]
        ):
            raise CheckoutUnavailable("PRODUCT_IDENTITY_CHANGED")
        if (
            row["expected_price_minor"] != f["configured_price_minor"]
            or row["expected_currency"] != f["currency"]
        ):
            raise CheckoutUnavailable("PRICE_EVIDENCE_MISMATCH")
        ids = [f["original_intent_id"]] + [
            r["successor_id"]
            for r in c.execute(
                "SELECT successor_id FROM evergreen_checkout_lineage WHERE namespace=%s AND original_transaction_id=%s",
                (NAMESPACE, f["original_intent_id"]),
            ).fetchall()
        ]
        if c.execute(
            "SELECT 1 FROM purchase_intents WHERE purchase_intent_id=ANY(%s) AND status='PURCHASED'",
            (ids,),
        ).fetchone():
            raise CheckoutUnavailable("PURCHASE_COMPLETE")
        if c.execute(
            """SELECT 1 FROM purchase_intents WHERE fanvue_account_id=%s AND telegram_user_id=%s
            AND status IN ('CREATED','PRESENTED','CLICKED') AND NOT(purchase_intent_id=ANY(%s))""",
            (row["fanvue_account_id"], row["telegram_user_id"], ids),
        ).fetchone():
            raise CheckoutUnavailable("CONFLICTING_OFFER")
        if f["fingerprint_reservation_id"]:
            r = c.execute(
                "SELECT * FROM fanvue_fingerprint_reservations WHERE fingerprint_reservation_id=%s FOR SHARE",
                (f["fingerprint_reservation_id"],),
            ).fetchone()
            if r["state"] == "PURCHASED":
                raise CheckoutUnavailable("PURCHASE_COMPLETE")
            if (
                r["exact_price_minor"] != f["final_price_minor"]
                or r["currency"] != f["currency"]
                or r["purchase_intent_id"] != f["original_intent_id"]
            ):
                raise CheckoutUnavailable("FINGERPRINT_CHANGED")
        mappings = c.execute(
            "SELECT * FROM telegram_identity_map WHERE telegram_user_id=%s AND is_active AND verification_status='VERIFIED' FOR SHARE",
            (row["telegram_user_id"],),
        ).fetchall()
        if len(mappings) > 1 or any(
            m["fanvue_account_id"] != row["fanvue_account_id"]
            or m["telegram_chat_id"] != row["telegram_chat_id"]
            for m in mappings
        ):
            raise CheckoutUnavailable("IDENTITY_MISMATCH")
        runtime = c.execute(
            "SELECT mode FROM runtime_control_records WHERE creator_profile_id=%s FOR SHARE",
            (str(row["creator_profile_id"]),),
        ).fetchone()
        if not runtime or runtime["mode"] != "LIVE":
            raise CheckoutUnavailable("COMMERCE_BLOCKED")
        # Relationship content-selling permission gates new outbound offers.
        # Restoring that permission after issuance does not revoke a customer's
        # existing grant. Checkout revocation, product, account/runtime, identity,
        # purchase and safety authorities remain independently enforced here.
        prospect = c.execute(
            "SELECT relationship_state FROM telegram_sales_prospects WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s FOR SHARE",
            (
                row["creator_profile_id"],
                row["fanvue_account_id"],
                row["telegram_user_id"],
            ),
        ).fetchone()
        block = ((prospect or {}).get("relationship_state") or {}).get(
            "telegramContactBlock"
        ) or {}
        if (
            block.get("active")
            or block.get("blocked")
            or block.get("state") == "PERMANENT_BLOCKED"
        ):
            raise CheckoutUnavailable("PURCHASE_NOT_ALLOWED")
        if mappings:
            if (
                row["external_fanvue_user_uuid"] is not None
                and row["external_fanvue_user_uuid"]
                != mappings[0]["external_fanvue_user_uuid"]
            ):
                raise CheckoutUnavailable("IDENTITY_MISMATCH")
            if c.execute(
                """SELECT 1 FROM purchase_intents WHERE creator_profile_id=%s AND fanvue_account_id=%s
                AND commercial_offering_id=%s AND external_fanvue_user_uuid=%s AND status='PURCHASED'""",
                (
                    row["creator_profile_id"],
                    row["fanvue_account_id"],
                    row["commercial_offering_id"],
                    mappings[0]["external_fanvue_user_uuid"],
                ),
            ).fetchone():
                raise CheckoutUnavailable("PURCHASE_COMPLETE")
            owned = c.execute(
                """SELECT 1 FROM commercial_offering_assets m WHERE m.offering_id=%s
                GROUP BY m.offering_id HAVING bool_and(EXISTS(SELECT 1 FROM provider_purchase_asset_ownership p
                WHERE p.content_item_id=m.asset_id AND p.fanvue_account_id=%s AND p.external_fanvue_user_uuid=%s))""",
                (
                    row["commercial_offering_id"],
                    row["fanvue_account_id"],
                    mappings[0]["external_fanvue_user_uuid"],
                ),
            ).fetchone()
            if owned:
                raise CheckoutUnavailable("PURCHASE_COMPLETE")
            from app.services.customer_interaction_safety_service import (
                CustomerInteractionSafetyService,
            )
            from app.repositories.customer_interaction_safety_repository import (
                CustomerInteractionSafetyRepository,
            )
            from app.repositories.ai_training_control_repository import (
                AiTrainingControlRepository,
            )
            from app.repositories.customer_abuse_review_repository import (
                CustomerAbuseReviewRepository,
            )

            @contextmanager
            def same():
                yield c

            safety = CustomerInteractionSafetyService(
                CustomerInteractionSafetyRepository(same),
                AiTrainingControlRepository(same),
                CustomerAbuseReviewRepository(same),
            )
            if not safety.decide(
                creator_profile_id=row["creator_profile_id"],
                fanvue_account_id=row["fanvue_account_id"],
                fanvue_user_id=mappings[0]["local_fanvue_user_id"],
            ).allowed:
                raise CheckoutUnavailable("PURCHASE_NOT_ALLOWED")
        return CheckoutEligibility(
            True, True, True, True, True, True, True, True, transaction.price
        )

    def expire(self, transaction, *, now, connection):
        connection.execute(
            "UPDATE purchase_intents SET status='EXPIRED',updated_at=%s WHERE purchase_intent_id=%s AND expires_at<=%s AND status IN ('CREATED','PRESENTED','CLICKED')",
            (now, transaction.transaction_id, now),
        )
        return self.load(transaction.transaction_id, connection=connection)

    def create_successor(
        self,
        predecessor,
        *,
        transaction_id,
        price,
        expires_at,
        idempotency_key,
        connection
    ):
        row = connection.execute(
            "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s",
            (predecessor.transaction_id,),
        ).fetchone()
        values = dict(
            row,
            purchase_intent_id=transaction_id,
            correlation_id=idempotency_key,
            expires_at=expires_at,
            created_metadata={
                **row["created_metadata"],
                "evergreen_original_intent_id": str(self.family["original_intent_id"]),
            },
        )
        repo = PurchaseIntentRepository()
        with connection.cursor() as cursor:
            repo._insert(cursor, values)
        return self.load(transaction_id, connection=connection)

    def confirm(self, grant, transaction, *, connection, now):
        connection.execute(
            "UPDATE purchase_intents SET status='CLICKED',clicked_at=COALESCE(clicked_at,%s),updated_at=%s WHERE purchase_intent_id=%s AND status IN ('CREATED','PRESENTED')",
            (now, now, transaction.transaction_id),
        )
        connection.execute(
            "UPDATE telegram_unlock_grants SET use_count=use_count+1,last_used_at=%s WHERE unlock_grant_id=%s",
            (now, grant.alias_id),
        )

    def validate_destination(self, destination, transaction):
        try:
            return (
                self.gateway._validated_fanvue_destination(destination) == destination
            )
        except Exception:
            return False


class CanonicalUnlockRuntime:
    def __init__(self, authority):
        self.authority = authority

    def recover_expired(self, grant, repository):
        with repository.serialize(NAMESPACE, grant.original_transaction_id) as c:
            latest = repository.latest(c, NAMESPACE, grant.original_transaction_id)
            if not latest:
                return
            self.authority.lock_scope(grant, connection=c)
            checked = self.authority.authenticate(
                self.authority.alias, grant.binding, connection=c
            )
            if checked.revoked:
                raise CheckoutUnavailable("GRANT_REVOKED")
            current = self.authority.load(latest["successor_id"], connection=c)
            self.authority.validate(grant, current, connection=c)
            c.commit()
            self.reconcile(current, operation_key=latest["successor_id"])
            with c.transaction():
                repository.runtime_result(
                    c,
                    NAMESPACE,
                    current.transaction_id,
                    state="READY",
                    reason="RECONCILED",
                )

    def reconcile(self, transaction, *, operation_key):
        try:
            return self._reconcile(transaction, operation_key=operation_key)
        except Exception as error:
            reason = (
                error.reason_code
                if isinstance(error, CheckoutUnavailable)
                else "PROVIDER_RECONCILIATION_FAILED"
            )
            with self.authority.gateway.connection_factory() as c:
                c.execute(
                    """UPDATE evergreen_provider_operations SET reason_code=%s,
                    state=CASE WHEN state='INVOKING' OR %s='PROVIDER_UNKNOWN' THEN 'UNKNOWN' ELSE state END,
                    updated_at=NOW() WHERE original_intent_id=%s""",
                    (reason, reason, self.authority.family["original_intent_id"]),
                )
            raise

    def validate_provider_acknowledgement(self, link):
        from decimal import Decimal, InvalidOperation

        f = self.authority.family
        try:
            exact = Decimal(str(link.get("price"))) == Decimal(f["final_price_minor"])
        except (InvalidOperation, ValueError):
            exact = False
        if not exact or sorted(link.get("mediaUuids") or []) != f["media_uuids"]:
            raise CheckoutUnavailable("PROVIDER_PRICE_OR_PRODUCT_MISMATCH")
        if not str(link.get("uuid") or "").strip():
            raise CheckoutUnavailable("PROVIDER_ACK_MISSING")

    def record_provider(self, c, root, link):
        self.validate_provider_acknowledgement(link)
        f = self.authority.family
        evidence = {
            "provider_resource_id": str(link["uuid"]),
            "provider_url": str(link["url"]),
            "price_minor": f["final_price_minor"],
            "currency": f["currency"],
            "media_uuids": f["media_uuids"],
        }
        encoded = json.dumps([evidence])
        key = uuid5(NAMESPACE_URL, "creator-os-evergreen-provider:" + str(root))
        c.execute(
            """INSERT INTO evergreen_provider_operations(original_intent_id,operation_id,state,
            provider_resource_id,provider_url,provider_evidence,reason_code)
            VALUES(%s,%s,'READY',%s,%s,%s::jsonb,'ACKNOWLEDGED') ON CONFLICT(original_intent_id) DO UPDATE SET
            state='READY',provider_resource_id=EXCLUDED.provider_resource_id,provider_url=EXCLUDED.provider_url,
            provider_evidence=CASE WHEN evergreen_provider_operations.provider_evidence @> EXCLUDED.provider_evidence
                THEN evergreen_provider_operations.provider_evidence ELSE evergreen_provider_operations.provider_evidence || EXCLUDED.provider_evidence END,
            reason_code='ACKNOWLEDGED',updated_at=NOW()""",
            (root, key, str(link["uuid"]), str(link["url"]), encoded),
        )

    def _reconcile(self, transaction, *, operation_key):
        a = self.authority
        g = a.gateway
        f = a.family
        root = f["original_intent_id"]
        if not f["fingerprint_reservation_id"]:
            with g.connection_factory() as c:
                row = c.execute(
                    "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s",
                    (root,),
                ).fetchone()
                publication = a.publication(c, row)
            client = g.client_factory(int(f["binding"]["fanvue_account_id"]))
            matches = [
                link
                for link in client.find_equivalent_media_link(
                    tuple(f["media_uuids"]), f["final_price_minor"]
                )
                if str(link.get("uuid")) == str(publication["external_product_id"])
            ]
            if len(matches) != 1:
                raise CheckoutUnavailable("PROVIDER_UNKNOWN")
            link = matches[0]
            destination = g._validated_fanvue_destination(link.get("url"))
            if destination != (
                publication["publication_metadata"].get("media_link") or {}
            ).get("url"):
                raise CheckoutUnavailable("PROVIDER_IDENTITY_CHANGED")
            with g.connection_factory() as c:
                self.record_provider(c, root, link)
            return destination
        key = uuid5(NAMESPACE_URL, "creator-os-evergreen-provider:" + str(root))
        with g.connection_factory() as c:
            c.execute(
                "INSERT INTO evergreen_provider_operations(original_intent_id,operation_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (root, key),
            )
            op = c.execute(
                "SELECT * FROM evergreen_provider_operations WHERE original_intent_id=%s FOR UPDATE",
                (root,),
            ).fetchone()
            old = c.execute(
                "SELECT * FROM fanvue_runtime_media_links WHERE fingerprint_reservation_id=%s",
                (f["fingerprint_reservation_id"],),
            ).fetchone()
        if old and old["state"] in (
            "PURCHASED",
            "DELETE_REQUESTED",
            "DELETED",
            "DELETE_FAILED",
            "ORPHANED",
        ):
            raise CheckoutUnavailable("PROVIDER_RESOURCE_RETIRED")
        client = g.client_factory(int(f["binding"]["fanvue_account_id"]))
        # A list miss after invocation or legacy evidence is never a create permit.
        matches = client.find_equivalent_media_link(
            tuple(f["media_uuids"]), f["final_price_minor"]
        )
        if len(matches) > 1:
            raise CheckoutUnavailable("PROVIDER_MATCH_AMBIGUOUS")
        if matches:
            link = matches[0]
        else:
            if op["state"] != "PENDING" or op["attempt_count"] or old:
                raise CheckoutUnavailable("PROVIDER_UNKNOWN")
            with g.connection_factory() as c:
                claim = c.execute(
                    "UPDATE evergreen_provider_operations SET state='INVOKING',attempt_count=1,updated_at=NOW() WHERE original_intent_id=%s AND state='PENDING' AND attempt_count=0 RETURNING *",
                    (root,),
                ).fetchone()
                if not claim:
                    raise CheckoutUnavailable("PROVIDER_UNKNOWN")
            try:
                link = client.create_media_link(
                    tuple(f["media_uuids"]), f["final_price_minor"]
                )
            except Exception as error:
                with g.connection_factory() as c:
                    c.execute(
                        "UPDATE evergreen_provider_operations SET state='UNKNOWN',reason_code='PROVIDER_UNKNOWN',updated_at=NOW() WHERE original_intent_id=%s",
                        (root,),
                    )
                raise CheckoutUnavailable("PROVIDER_UNKNOWN") from error
        provider_id = str(link.get("uuid") or "").strip()
        url = g._validated_fanvue_destination(link.get("url"))
        if not provider_id:
            raise CheckoutUnavailable("PROVIDER_ACK_MISSING")
        if (
            old
            and old["provider_media_link_uuid"]
            and old["provider_media_link_uuid"] != provider_id
        ):
            raise CheckoutUnavailable("PROVIDER_IDENTITY_CHANGED")
        # Canonical runtime/reservation remain the settlement anchor. No allocator.
        with g.connection_factory() as c:
            from app.services.evergreen_purchase_attribution import family_target

            target = family_target(c, root)
            paid = c.execute(
                "SELECT status FROM purchase_intents WHERE purchase_intent_id=%s",
                (target,),
            ).fetchone()
            reserved = c.execute(
                "SELECT state FROM fanvue_fingerprint_reservations WHERE fingerprint_reservation_id=%s FOR UPDATE",
                (f["fingerprint_reservation_id"],),
            ).fetchone()
            if paid["status"] == "PURCHASED" or reserved["state"] == "PURCHASED":
                raise CheckoutUnavailable("PURCHASE_COMPLETE")
            self.record_provider(c, root, link)
            c.execute(
                """INSERT INTO fanvue_runtime_media_links(runtime_media_link_id,purchase_intent_id,
                fingerprint_reservation_id,creation_operation_key,expires_at,state,provider_media_link_uuid,provider_url)
                VALUES(%s,%s,%s,%s,%s,'ACTIVE',%s,%s)
                ON CONFLICT(fingerprint_reservation_id) DO UPDATE SET state='ACTIVE'
                WHERE fanvue_runtime_media_links.provider_media_link_uuid=EXCLUDED.provider_media_link_uuid AND fanvue_runtime_media_links.state<>'PURCHASED' """,
                (
                    key,
                    root,
                    f["fingerprint_reservation_id"],
                    key,
                    max(transaction.expires_at, g.clock() + g.runtime_ttl),
                    provider_id,
                    url,
                ),
            )
            c.execute(
                "UPDATE fanvue_fingerprint_reservations SET state='ACTIVE' WHERE fingerprint_reservation_id=%s AND state IN ('RESERVED','RETIRED')",
                (f["fingerprint_reservation_id"],),
            )
        return url


def resolve_alias(gateway, alias):
    with gateway.connection_factory() as c:
        row = c.execute(
            "SELECT i.* FROM telegram_unlock_grants g JOIN purchase_intents i USING(purchase_intent_id) WHERE g.public_alias_hash=%s",
            (token_digest(alias),),
        ).fetchone()
    if not row:
        raise CheckoutUnavailable("ALIAS_INVALID")
    authority = CanonicalUnlockAuthority(gateway, alias)
    service = EvergreenCheckoutService(
        namespace=NAMESPACE,
        authority=authority,
        runtime=CanonicalUnlockRuntime(authority),
        repository=EvergreenCheckoutRepository(
            connection_factory=gateway.connection_factory
        ),
        clock=gateway.clock,
        lifetime=timedelta(
            hours=(
                24
                if row["created_metadata"].get("presentation_origin")
                == "HUMAN_OPERATOR_PRESENTED"
                else 72
            )
        ),
    )
    result = service.resolve(alias, binding=binding(row))
    return result.destination
