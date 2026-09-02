"""Bundle Studio persistence adapter for the shared selective-blur teaser workflow."""
from app.repositories.photoshoot_bundle_teaser_repository import PhotoshootBundleTeaserRepository


class BundleStudioTeaserRepository(PhotoshootBundleTeaserRepository):
    def get(self, deliverable_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.bundle_studio_teasers WHERE bundle_id=%s", (deliverable_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def upsert(self, *, deliverable_id, creator_profile_id, source_asset_id, teaser_asset_id,
               mask_path, mask_width, mask_height, blur_strength):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.bundle_studio_teasers
                (bundle_id,creator_profile_id,source_asset_id,teaser_asset_id,mask_path,mask_width,mask_height,blur_strength)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(bundle_id) DO UPDATE SET
                source_asset_id=EXCLUDED.source_asset_id,teaser_asset_id=EXCLUDED.teaser_asset_id,
                mask_path=EXCLUDED.mask_path,mask_width=EXCLUDED.mask_width,mask_height=EXCLUDED.mask_height,
                blur_strength=EXCLUDED.blur_strength,updated_at=NOW() RETURNING *""",
                (deliverable_id,creator_profile_id,source_asset_id,teaser_asset_id,mask_path,mask_width,mask_height,blur_strength))
            return dict(cur.fetchone())

    def integrity_conflicts(self, *, deliverable_id, teaser_asset_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""SELECT FALSE AS photoshoot_member, EXISTS(
              SELECT 1 FROM public.commercial_offerings o JOIN public.commercial_offering_assets m USING(offering_id)
              WHERE o.source_bundle_studio_bundle_id=%s AND m.asset_id=%s) AS paid_bundle_member""",
              (deliverable_id, teaser_asset_id))
            return dict(cur.fetchone())
