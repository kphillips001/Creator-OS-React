"""Read-only projection of existing ownership authorities."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.database import get_db_connection
from app.models.ownership_intelligence import (
    OwnershipEvidence,
    OwnershipIdentity,
    OwnershipLifecycle,
    OwnershipSource,
    immutable_details,
)


class OwnershipIntelligenceRepository:
    def __init__(self, connection_factory=get_db_connection) -> None:
        self.connection_factory = connection_factory

    def evidence_for(self, identity: OwnershipIdentity) -> tuple[OwnershipEvidence, ...]:
        evidence: list[OwnershipEvidence] = []
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                evidence.extend(self._offering_evidence(cursor, identity))
                evidence.extend(self._entitlement_evidence(cursor, identity))
                evidence.extend(self._legacy_evidence(cursor, identity))
        return tuple(evidence)

    def offering_assets(self, offering_id, *, creator_profile_id: int) -> tuple[int, ...]:
        return self._composition(
            """SELECT member.asset_id
               FROM public.commercial_offerings offering
               JOIN public.commercial_offering_assets member
                 ON member.offering_id=offering.offering_id
               WHERE offering.offering_id=%s
                 AND offering.creator_profile_id=%s
               ORDER BY member.position""",
            (UUID(str(offering_id)), int(creator_profile_id)),
        )

    def product_assets(self, product_id, *, creator_profile_id: int) -> tuple[int, ...]:
        return self._composition(
            """SELECT member.asset_id
               FROM public.products product
               JOIN public.product_assets member ON member.product_id=product.id
               WHERE product.id=%s AND product.creator_profile_id=%s
               ORDER BY member.position""",
            (UUID(str(product_id)), int(creator_profile_id)),
        )

    def session_assets(self, session_id, *, creator_profile_id: int) -> dict:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT session.commercial_foundation_reference,
                              COALESCE(array_agg(DISTINCT membership.asset_id)
                                FILTER (WHERE membership.asset_id IS NOT NULL),
                                ARRAY[]::bigint[]) AS represented_asset_ids
                       FROM public.sales_sessions session
                       LEFT JOIN public.photoshoot_asset_memberships membership
                         ON membership.photoshoot_session_id=
                            session.commercial_foundation_reference
                        AND membership.approved=TRUE
                       WHERE session.sales_session_id=%s
                         AND session.creator_profile_id=%s
                       GROUP BY session.sales_session_id""",
                    (UUID(str(session_id)), int(creator_profile_id)),
                )
                session = cursor.fetchone()
                if not session:
                    return {}
                cursor.execute(
                    """SELECT link.purchase_intent_id,link.sequence_index,
                              link.associated_at,
                              array_agg(member.asset_id ORDER BY member.position)
                                AS asset_ids
                       FROM public.sales_session_purchase_intents link
                       JOIN public.purchase_intents intent
                         ON intent.purchase_intent_id=link.purchase_intent_id
                       JOIN public.commercial_offering_assets member
                         ON member.offering_id=intent.commercial_offering_id
                       WHERE link.sales_session_id=%s
                         AND intent.creator_profile_id=%s
                         AND intent.status='PURCHASED'
                         AND intent.attribution_result='ATTRIBUTED'
                       GROUP BY link.purchase_intent_id,link.sequence_index,
                                link.associated_at
                       ORDER BY link.sequence_index,link.associated_at,
                                link.purchase_intent_id""",
                    (UUID(str(session_id)), int(creator_profile_id)),
                )
                chronology = tuple(dict(row) for row in cursor.fetchall())
                purchased = tuple(dict.fromkeys(
                    int(asset_id)
                    for row in chronology for asset_id in row["asset_ids"]
                ))
        return {
            "foundation": session["commercial_foundation_reference"],
            "represented_asset_ids": tuple(sorted(
                int(value) for value in session["represented_asset_ids"]
            )),
            "purchased_asset_ids": purchased,
            "purchase_chronology": chronology,
        }

    def bundle_compositions(self, *, creator_profile_id: int) -> tuple[dict, ...]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT offering.offering_id,offering.title,
                              array_agg(member.asset_id ORDER BY member.position)
                                AS asset_ids
                       FROM public.commercial_offerings offering
                       JOIN public.commercial_offering_assets member
                         ON member.offering_id=offering.offering_id
                       WHERE offering.creator_profile_id=%s
                         AND offering.offering_type='BUNDLE'
                         AND offering.status<>'ARCHIVED'
                       GROUP BY offering.offering_id
                       ORDER BY offering.created_at DESC,offering.offering_id""",
                    (int(creator_profile_id),),
                )
                return tuple(dict(row) for row in cursor.fetchall())

    def customer_session_ids(self, identity: OwnershipIdentity) -> tuple[UUID, ...]:
        clauses, params = [], [
            identity.creator_profile_id, identity.fanvue_account_id,
        ]
        if identity.external_fanvue_user_uuid is not None:
            clauses.append("external_fanvue_user_uuid=%s")
            params.append(identity.external_fanvue_user_uuid)
        if identity.legacy_fanvue_user_id is not None:
            try:
                legacy_id = int(identity.legacy_fanvue_user_id)
            except (TypeError, ValueError):
                legacy_id = None
            if legacy_id is not None:
                clauses.append("fanvue_user_id=%s")
                params.append(legacy_id)
        if not clauses:
            return ()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT sales_session_id
                        FROM public.sales_sessions
                        WHERE creator_profile_id=%s AND fanvue_account_id=%s
                          AND ({' OR '.join(clauses)})
                        ORDER BY started_at,sales_session_id""",
                    tuple(params),
                )
                return tuple(
                    UUID(str(row["sales_session_id"]))
                    for row in cursor.fetchall()
                )

    def _offering_evidence(self, cursor, identity):
        clause, values, path = self._purchase_identity(identity)
        if not clause:
            return ()
        cursor.execute(
            f"""SELECT intent.purchase_intent_id,intent.purchased_at,
                       intent.commercial_offering_id,intent.status,
                       intent.attribution_result,
                       array_agg(member.asset_id ORDER BY member.position)
                         AS asset_ids,
                       link.sales_session_id
                FROM public.purchase_intents intent
                JOIN public.commercial_offerings offering
                  ON offering.offering_id=intent.commercial_offering_id
                JOIN public.commercial_offering_assets member
                  ON member.offering_id=offering.offering_id
                LEFT JOIN public.sales_session_purchase_intents link
                  ON link.purchase_intent_id=intent.purchase_intent_id
                WHERE intent.creator_profile_id=%s
                  AND intent.fanvue_account_id=%s AND {clause}
                GROUP BY intent.purchase_intent_id,link.sales_session_id""",
            (
                identity.creator_profile_id, identity.fanvue_account_id,
                *values,
            ),
        )
        values = []
        for row in cursor.fetchall():
            purchased = (
                row["status"] == "PURCHASED"
                and row["attribution_result"] == "ATTRIBUTED"
            )
            lifecycle = {
                "ABANDONED": OwnershipLifecycle.ABANDONED,
                "EXPIRED": OwnershipLifecycle.EXPIRED,
                "CANCELLED": OwnershipLifecycle.CANCELLED,
                "SUPERSEDED": OwnershipLifecycle.SUPERSEDED,
                "UNKNOWN": OwnershipLifecycle.AMBIGUOUS,
            }.get(
                row["status"],
                OwnershipLifecycle.PURCHASED if purchased
                else OwnershipLifecycle.AMBIGUOUS
                if row["attribution_result"] == "UNKNOWN"
                else OwnershipLifecycle.PENDING,
            )
            values.append(OwnershipEvidence(
                source=OwnershipSource.OFFERING_PURCHASE,
                lifecycle=lifecycle, identity_path=path,
                supporting_record_id=str(row["purchase_intent_id"]),
                creator_profile_id=identity.creator_profile_id,
                fanvue_account_id=identity.fanvue_account_id,
                offering_id=UUID(str(row["commercial_offering_id"])),
                sales_session_id=(
                    UUID(str(row["sales_session_id"]))
                    if row.get("sales_session_id") else None
                ),
                asset_ids=tuple(int(item) for item in row["asset_ids"]),
                proves_ownership=purchased,
                details=immutable_details({
                    "status": row["status"],
                    "attributionResult": row["attribution_result"],
                    "purchasedAt": (
                        row["purchased_at"].isoformat()
                        if row.get("purchased_at") else None
                    ),
                }),
            ))
        return tuple(values)

    def _entitlement_evidence(self, cursor, identity):
        clauses, parameters = [], []
        if identity.legacy_fanvue_user_id is not None:
            clauses.append(
                "(entitlement.legacy_fanvue_account_id=%s "
                "AND entitlement.legacy_fanvue_user_id=%s)"
            )
            parameters.extend([
                identity.fanvue_account_id, identity.legacy_fanvue_user_id,
            ])
        if identity.core_user_id is not None:
            clauses.append("entitlement.core_user_id=%s")
            parameters.append(identity.core_user_id)
        if not clauses:
            return ()
        cursor.execute(
            f"""SELECT entitlement.*,product.creator_profile_id,
                       COALESCE(array_agg(member.asset_id ORDER BY member.position)
                         FILTER (WHERE member.asset_id IS NOT NULL),
                         ARRAY[]::bigint[]) AS asset_ids
                FROM public.customer_entitlements entitlement
                JOIN public.products product ON product.id=entitlement.product_id
                LEFT JOIN public.product_assets member
                  ON member.product_id=product.id
                WHERE ({' OR '.join(clauses)})
                  AND product.creator_profile_id=%s
                GROUP BY entitlement.id,product.creator_profile_id""",
            (*parameters, identity.creator_profile_id),
        )
        now = datetime.now(timezone.utc)
        values = []
        for row in cursor.fetchall():
            lifecycle = self._entitlement_lifecycle(row, now)
            paths = []
            if (
                identity.core_user_id is not None
                and row.get("core_user_id") == identity.core_user_id
            ):
                paths.append((
                    OwnershipSource.CORE_USER_ENTITLEMENT, "core_user_id",
                ))
            if (
                identity.legacy_fanvue_user_id is not None
                and row.get("legacy_fanvue_account_id")
                == identity.fanvue_account_id
                and str(row.get("legacy_fanvue_user_id"))
                == identity.legacy_fanvue_user_id
            ):
                paths.append((
                    OwnershipSource.PRODUCT_ENTITLEMENT,
                    "legacy_fanvue_identity",
                ))
            for source, path in paths:
                values.append(OwnershipEvidence(
                    source=source, lifecycle=lifecycle, identity_path=path,
                    supporting_record_id=str(row["id"]),
                    creator_profile_id=identity.creator_profile_id,
                    fanvue_account_id=identity.fanvue_account_id,
                    product_id=UUID(str(row["product_id"])),
                    asset_ids=tuple(int(item) for item in row["asset_ids"]),
                    proves_ownership=lifecycle in {
                        OwnershipLifecycle.ACTIVE,
                        OwnershipLifecycle.FULFILLED,
                    },
                    details=immutable_details({
                        "status": row["status"],
                        "sourceType": row["source_type"],
                        "expiresAt": (
                            row["expires_at"].isoformat()
                            if row.get("expires_at") else None
                        ),
                    }),
                ))
        return tuple(values)

    def _legacy_evidence(self, cursor, identity):
        if identity.legacy_fanvue_user_id is None:
            return ()
        cursor.execute(
            """SELECT id,content_item_id,content_tag,usage_type
               FROM public.content_usage_log
               WHERE fanvue_account_id=%s AND fanvue_user_id=%s
                 AND usage_type=ANY(%s)""",
            (
                identity.fanvue_account_id, identity.legacy_fanvue_user_id,
                [
                    "ppv_purchased", "content_unlocked", "content_owned",
                    "purchase", "unlock", "owned",
                ],
            ),
        )
        return tuple(
            OwnershipEvidence(
                source=OwnershipSource.LEGACY_OWNERSHIP,
                lifecycle=(
                    OwnershipLifecycle.ACTIVE
                    if row.get("content_item_id") is not None
                    else OwnershipLifecycle.INCOMPLETE
                ),
                identity_path="legacy_fanvue_identity",
                supporting_record_id=str(row["id"]),
                creator_profile_id=identity.creator_profile_id,
                fanvue_account_id=identity.fanvue_account_id,
                asset_ids=(
                    (int(row["content_item_id"]),)
                    if row.get("content_item_id") is not None else ()
                ),
                proves_ownership=row.get("content_item_id") is not None,
                details=immutable_details({
                    "usageType": row["usage_type"],
                    "contentTag": row.get("content_tag"),
                    "unresolvedContentTag": (
                        row.get("content_tag")
                        if row.get("content_item_id") is None else None
                    ),
                }),
            )
            for row in cursor.fetchall()
        )

    def _composition(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return tuple(int(row["asset_id"]) for row in cursor.fetchall())

    @staticmethod
    def _purchase_identity(identity):
        if identity.external_fanvue_user_uuid is not None:
            return (
                "intent.external_fanvue_user_uuid=%s",
                (identity.external_fanvue_user_uuid,),
                "external_fanvue_user_uuid",
            )
        if identity.telegram_user_id is not None:
            return (
                "intent.telegram_user_id=%s",
                (identity.telegram_user_id,),
                "telegram_user_id",
            )
        return None, (), "unresolved"

    @staticmethod
    def _entitlement_lifecycle(row, now):
        status = str(row["status"]).lower()
        valid_from = row.get("valid_from")
        expires = row.get("expires_at")
        if valid_from is not None and valid_from > now:
            return OwnershipLifecycle.PENDING
        if expires is not None and expires <= now:
            return OwnershipLifecycle.EXPIRED
        if status == "active":
            return OwnershipLifecycle.ACTIVE
        return {
            "fulfilled": OwnershipLifecycle.FULFILLED,
            "expired": OwnershipLifecycle.EXPIRED,
            "revoked": OwnershipLifecycle.REVOKED,
            "refunded": OwnershipLifecycle.REFUNDED,
            "pending": OwnershipLifecycle.PENDING,
            "cancelled": OwnershipLifecycle.CANCELLED,
        }.get(status, OwnershipLifecycle.INCOMPLETE)
