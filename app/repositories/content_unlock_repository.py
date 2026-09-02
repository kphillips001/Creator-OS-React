"""Account-scoped persistence for verified provider content unlocks."""
from __future__ import annotations

from app.database import get_db_connection


def log_content_unlock(
    fanvue_account_id: int, fanvue_user_id, content_tag: str | None = None,
    fanvue_media_uuid: str | None = None, purchase_amount: float = 0,
    content_item_id: int | None = None, commercial_offering_id=None,
    provider_resource_id: str | None = None,
    connection_factory=get_db_connection,
):
    """Persist exact ownership or a non-owning incomplete evidence row."""
    normalized_user_id = str(fanvue_user_id).strip() if fanvue_user_id is not None else ""
    if not fanvue_account_id or not normalized_user_id:
        return {"success": False, "reason": "missing_account_or_user_id",
                "ownership_resolved": False, "rows": ()}
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            asset_ids, resolution = _resolve_asset_ids(
                cursor, fanvue_account_id=int(fanvue_account_id),
                content_item_id=content_item_id,
                fanvue_media_uuid=fanvue_media_uuid,
                commercial_offering_id=commercial_offering_id,
                provider_resource_id=provider_resource_id,
            )
            rows = []
            for asset_id in asset_ids or (None,):
                cursor.execute(
                    """INSERT INTO public.content_usage_log (
                           content_item_id,fanvue_account_id,fanvue_user_id,
                           content_tag,fanvue_media_uuid,usage_type,
                           purchase_amount,purchased_at,metadata,created_at
                       ) VALUES (%s,%s,%s,%s,%s,'content_unlocked',%s,NOW(),
                           jsonb_build_object('ownershipResolution',%s,
                             'commercialOfferingId',%s,'providerResourceId',%s),NOW())
                       RETURNING *""",
                    (asset_id, int(fanvue_account_id), normalized_user_id,
                     content_tag, fanvue_media_uuid, purchase_amount, resolution,
                     str(commercial_offering_id) if commercial_offering_id else None,
                     provider_resource_id),
                )
                row = cursor.fetchone()
                if row:
                    rows.append(dict(row))
    return {"success": True, "ownership_resolved": bool(asset_ids),
            "resolution": resolution, "asset_ids": tuple(asset_ids),
            "rows": tuple(rows),
            "reason": None if asset_ids else "exact_content_attribution_unavailable"}


def _resolve_asset_ids(cursor, *, fanvue_account_id, content_item_id,
                       fanvue_media_uuid, commercial_offering_id,
                       provider_resource_id):
    if content_item_id is not None:
        cursor.execute(
            """SELECT content.id FROM public.content_items content
                WHERE content.id=%s AND (
                    content.fanvue_account_id=%s OR EXISTS (
                        SELECT 1 FROM public.creator_profiles creator
                         WHERE creator.id=content.creator_profile_id
                           AND creator.fanvue_account_id=%s))""",
            (int(content_item_id), fanvue_account_id, fanvue_account_id),
        )
        return ((int(content_item_id),), "EXPLICIT_CONTENT_ITEM") if cursor.fetchone() else ((), "EXPLICIT_CONTENT_ITEM_NOT_FOUND")
    offering_id = commercial_offering_id
    if offering_id is None and provider_resource_id:
        cursor.execute(
            """SELECT publication.commercial_offering_id
                 FROM public.commercial_publications publication
                 JOIN public.commercial_offerings offering ON offering.offering_id=publication.commercial_offering_id
                 JOIN public.creator_profiles creator ON creator.id=offering.creator_profile_id
                WHERE publication.external_product_id=%s AND creator.fanvue_account_id=%s LIMIT 2""",
            (str(provider_resource_id), fanvue_account_id),
        )
        matches = cursor.fetchall()
        if len(matches) == 1:
            offering_id = matches[0]["commercial_offering_id"]
        elif len(matches) > 1:
            return (), "AMBIGUOUS_PROVIDER_RESOURCE"
    if offering_id is not None:
        cursor.execute(
            """SELECT member.asset_id
                 FROM public.commercial_offerings offering
                 JOIN public.creator_profiles creator ON creator.id=offering.creator_profile_id
                 JOIN public.commercial_offering_assets member ON member.offering_id=offering.offering_id
                WHERE offering.offering_id=%s AND creator.fanvue_account_id=%s
                ORDER BY member.position""",
            (offering_id, fanvue_account_id),
        )
        assets = tuple(int(row["asset_id"]) for row in cursor.fetchall())
        return (assets, "COMMERCIAL_OFFERING_ASSETS") if assets else ((), "OFFERING_NOT_RESOLVED")
    if fanvue_media_uuid:
        cursor.execute(
            """SELECT DISTINCT content_item_id FROM public.cms_fanvue_upload_links
                WHERE fanvue_account_id=%s
                  AND %s IN (fanvue_media_uuid,fanvue_preview_media_uuid,fanvue_full_media_uuid)
                  AND content_item_id IS NOT NULL""",
            (fanvue_account_id, str(fanvue_media_uuid)),
        )
        assets = tuple(int(row["content_item_id"]) for row in cursor.fetchall())
        if len(assets) == 1:
            return assets, "ACCOUNT_SCOPED_MEDIA_UPLOAD"
        if len(assets) > 1:
            return (), "AMBIGUOUS_MEDIA_UPLOAD"
    return (), "EXACT_CONTENT_UNAVAILABLE"
