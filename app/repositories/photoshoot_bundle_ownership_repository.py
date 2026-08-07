"""Read-only canonical composition for one Photoshoot Bundle."""

from __future__ import annotations

from uuid import UUID

from app.database import get_db_connection


class PhotoshootBundleOwnershipRepository:
    def __init__(self, connection_factory=get_db_connection) -> None:
        self.connection_factory = connection_factory

    def context(self, deliverable_id, *, creator_profile_id: int) -> dict | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT deliverable.deliverable_id,
                              deliverable.photoshoot_session_id,
                              deliverable.selling_mode,offering.offering_id,
                              offering.price_minor,offering.currency,
                              COALESCE(array_agg(member.asset_id ORDER BY member.position)
                                FILTER (WHERE member.asset_id IS NOT NULL),
                                ARRAY[]::bigint[]) AS paid_asset_ids,
                              teaser.teaser_asset_id
                       FROM public.photoshoot_commerce_deliverables deliverable
                       LEFT JOIN public.commercial_offerings offering
                         ON offering.source_photoshoot_deliverable_id=
                            deliverable.deliverable_id
                        AND offering.offering_type='BUNDLE'
                        AND offering.status<>'ARCHIVED'
                       LEFT JOIN public.commercial_offering_assets member
                         ON member.offering_id=offering.offering_id
                       LEFT JOIN public.photoshoot_bundle_teasers teaser
                         ON teaser.deliverable_id=deliverable.deliverable_id
                       WHERE deliverable.deliverable_id=%s
                         AND deliverable.creator_profile_id=%s
                       GROUP BY deliverable.deliverable_id,
                                deliverable.photoshoot_session_id,
                                deliverable.selling_mode,offering.offering_id,
                                offering.price_minor,offering.currency,
                                teaser.teaser_asset_id""",
                    (UUID(str(deliverable_id)), int(creator_profile_id)),
                )
                rows = tuple(dict(row) for row in cursor.fetchall())
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError("Photoshoot has more than one active Bundle offering.")
        row = rows[0]
        row["paid_asset_ids"] = tuple(
            int(value) for value in row["paid_asset_ids"]
        )
        return row
