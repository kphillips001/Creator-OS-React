"""Persistence for destination-resolved, domain-neutral commercial teasers."""
import json
from uuid import uuid4
from app.database import get_db_connection


class CommercialTeaserRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory = connection_factory

    def get(self, source_asset_id, distribution_use):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.commercial_teasers WHERE source_asset_id=%s AND distribution_use=%s", (source_asset_id, distribution_use))
            row = cur.fetchone()
        return dict(row) if row else None

    def list_for_asset(self, source_asset_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.commercial_teasers WHERE source_asset_id=%s ORDER BY distribution_use", (source_asset_id,))
            return tuple(dict(row) for row in cur.fetchall())

    def upsert(self, *, creator_profile_id, source_asset_id, derived_asset_id, derivative_path,
               teaser_style, distribution_use, mask_path=None, mask_width=None, mask_height=None,
               mask_version=None, blur_strength=None, metadata=None):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.commercial_teasers
              (teaser_id,creator_profile_id,source_asset_id,derived_asset_id,derivative_path,
               teaser_style,distribution_use,mask_path,mask_width,mask_height,mask_version,
               blur_strength,status,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'READY',%s::jsonb)
              ON CONFLICT (source_asset_id,distribution_use) DO UPDATE SET
               derived_asset_id=EXCLUDED.derived_asset_id,derivative_path=EXCLUDED.derivative_path,
               teaser_style=EXCLUDED.teaser_style,mask_path=EXCLUDED.mask_path,
               mask_width=EXCLUDED.mask_width,mask_height=EXCLUDED.mask_height,
               mask_version=EXCLUDED.mask_version,blur_strength=EXCLUDED.blur_strength,
               status='READY',metadata=EXCLUDED.metadata,updated_at=now() RETURNING *""",
              (uuid4(),creator_profile_id,source_asset_id,derived_asset_id,str(derivative_path),teaser_style,
               distribution_use,str(mask_path) if mask_path else None,mask_width,mask_height,mask_version,
               blur_strength,json.dumps(metadata or {})))
            return dict(cur.fetchone())

    def create_asset(self, *, creator_profile_id, path, source_asset_id, metadata):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.content_items
              (file_path,file_name,classification,status,is_active,ready_for_rotation,upload_intent,
               requires_nudenet,requires_blur,requires_vision,creator_profile_id,local_vault_path,media_metadata)
              VALUES (%s,%s,'promotional_teaser','approved',TRUE,FALSE,'none',FALSE,FALSE,FALSE,%s,%s,%s::jsonb) RETURNING id""",
              (str(path),path.name,creator_profile_id,str(path),json.dumps(metadata)))
            return int(cur.fetchone()["id"])

    def update_asset(self, asset_id, *, path, metadata):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("UPDATE public.content_items SET file_path=%s,file_name=%s,local_vault_path=%s,media_metadata=%s::jsonb,updated_at=now() WHERE id=%s RETURNING id",
                        (str(path),path.name,str(path),json.dumps(metadata),asset_id))
            return bool(cur.fetchone())
