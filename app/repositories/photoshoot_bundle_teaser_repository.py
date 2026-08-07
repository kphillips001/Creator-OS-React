"""Persistence for the one authoritative promotional teaser per Bundle Photoshoot."""

import json
from app.database import get_db_connection


class PhotoshootBundleTeaserRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory = connection_factory

    def get(self, deliverable_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.photoshoot_bundle_teasers WHERE deliverable_id=%s", (deliverable_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def upsert(self, *, deliverable_id, creator_profile_id, source_asset_id, teaser_asset_id,
               mask_path, mask_width, mask_height, blur_strength):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.photoshoot_bundle_teasers
                (deliverable_id,creator_profile_id,source_asset_id,teaser_asset_id,
                 mask_path,mask_width,mask_height,blur_strength)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (deliverable_id) DO UPDATE SET
                 source_asset_id=EXCLUDED.source_asset_id,teaser_asset_id=EXCLUDED.teaser_asset_id,
                 mask_path=EXCLUDED.mask_path,mask_width=EXCLUDED.mask_width,
                 mask_height=EXCLUDED.mask_height,blur_strength=EXCLUDED.blur_strength,
                 updated_at=now() RETURNING *""", (deliverable_id,creator_profile_id,
                 source_asset_id,teaser_asset_id,mask_path,mask_width,mask_height,blur_strength))
            return dict(cur.fetchone())

    def create_asset(self, *, creator_profile_id, path, source_asset_id, metadata):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.content_items
                (file_path,file_name,classification,status,is_active,ready_for_rotation,
                 upload_intent,requires_nudenet,requires_blur,requires_vision,
                 creator_profile_id,local_vault_path,media_metadata)
                VALUES (%s,%s,'promotional_teaser','approved',TRUE,FALSE,'none',FALSE,FALSE,FALSE,
                        %s,%s,%s::jsonb) RETURNING id""",
                (str(path), path.name,creator_profile_id,str(path),json.dumps(metadata)))
            return int(cur.fetchone()["id"])

    def update_asset(self, asset_id, *, path, metadata):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE public.content_items SET file_path=%s,file_name=%s,
                local_vault_path=%s,media_metadata=%s::jsonb,updated_at=now()
                WHERE id=%s RETURNING id""", (str(path),path.name,str(path),json.dumps(metadata),asset_id))
            return bool(cur.fetchone())

    def integrity_conflicts(self, *, deliverable_id, teaser_asset_id):
        """Return structural roles that would make a teaser paid/original content."""
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT
                    EXISTS (
                      SELECT 1 FROM public.photoshoot_asset_memberships membership
                      WHERE membership.asset_id=%s
                    ) AS photoshoot_member,
                    EXISTS (
                      SELECT 1 FROM public.commercial_offerings offering
                      JOIN public.commercial_offering_assets member
                        ON member.offering_id=offering.offering_id
                      WHERE offering.source_photoshoot_deliverable_id=%s
                        AND member.asset_id=%s
                    ) AS paid_bundle_member""",
                (teaser_asset_id, deliverable_id, teaser_asset_id),
            )
            return dict(cur.fetchone())
