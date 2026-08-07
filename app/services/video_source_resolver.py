"""Resolve client source identities into owned canonical media."""
from pathlib import Path
import os
import hashlib
from app.repositories.asset_repository import AssetRepository
from app.database import get_db_connection
from app.services.generation_library_service import GenerationLibraryService


class VideoSourceResolver:
    supported_types = ("generation","photoshoot_shot","asset","edit_result","generated_video","upload")
    def __init__(self, asset_repository=None, connection_factory=get_db_connection, generation_library=None): self.assets=asset_repository or AssetRepository(); self.connection_factory=connection_factory; self.generations=generation_library or GenerationLibraryService()

    def resolve(self, *, source_type, source_id, creator_profile_id, account_id=None):
        if source_type not in self.supported_types: raise ValueError("Unsupported Video Studio source type.")
        if source_type=="generated_video":
            with self.connection_factory() as conn,conn.cursor() as cur:
                cur.execute("SELECT * FROM public.generated_media WHERE media_id=%s AND creator_profile_id=%s AND media_type='video'",(source_id,creator_profile_id)); media=cur.fetchone()
            if not media: raise ValueError("Generated video was not found for this Creator Profile.")
            path=Path(media["media_path"]); stat=path.stat()
            version=hashlib.sha256(f"{source_id}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()
            public_base=os.getenv("CREATOR_OS_PUBLIC_BASE_URL","").rstrip("/")
            return {"source_type":source_type,"source_id":str(source_id),"source_asset_id":None,"source_media_type":"video","source_version":version,"physical_path":str(path),"visual_reference_path":media.get("poster_path"),"provider_reference_url":f"{public_base}/api/v1/video-studio/media/{source_id}" if public_base else None,"lineage":{"generated_media_id":str(source_id)},"context":{"duration_seconds":float(media["duration_seconds"] or 0),"extension":True}}
        if source_type in {"generation","edit_result","photoshoot_shot"}:
            try: record=self.generations.get(str(source_id))
            except KeyError: record=None
            if record is not None:
                if int(record.creator_profile_id)!=int(creator_profile_id): raise ValueError("Source generation was not found for this Creator Profile.")
                reference=str(record.output_reference); path=Path(reference)
                stat=path.stat() if path.exists() else None
                version=hashlib.sha256(f"{record.image_id}:{reference}:{stat.st_size if stat else record.generation_result_id}:{stat.st_mtime_ns if stat else record.updated_at}".encode()).hexdigest()
                return {"source_type":source_type,"source_id":str(source_id),"source_asset_id":record.imported_asset_id,"source_media_type":"image","source_version":version,"physical_path":reference,"provider_reference_url":reference,"lineage":{"generation_id":record.image_id,"photoshoot_session_id":record.photoshoot_session_id,"photoshoot_request_id":record.photoshoot_request_id},"context":{"creative_mode":record.creative_mode,"prompt_summary":record.prompt_text[:500]}}
        # Registered workflows resolve through the canonical Asset authority.
        try: asset_id=int(source_id)
        except (TypeError,ValueError) as error: raise ValueError("A canonical Asset ID is required for this source.") from error
        asset=self.assets.get_by_id(asset_id)
        if not asset or int(asset.creator_profile_id or 0)!=int(creator_profile_id): raise ValueError("Source asset was not found for this Creator Profile.")
        path=Path(asset.local_vault_path or asset.file_path)
        stat=path.stat() if path.exists() else None
        version=hashlib.sha256(f"{asset.id}:{path}:{stat.st_size if stat else 0}:{stat.st_mtime_ns if stat else 0}".encode()).hexdigest()
        public_base=os.getenv("CREATOR_OS_PUBLIC_BASE_URL","").rstrip("/")
        provider_reference=f"{public_base}/api/v1/assets/{asset.id}/media" if asset.media_type=="video" and public_base else None
        return {"source_type":source_type,"source_id":str(source_id),"source_asset_id":asset.id,
            "source_media_type":asset.media_type,"source_version":version,"physical_path":str(path),"provider_reference_url":provider_reference,
            "lineage":{"asset_id":asset.id,"origin_type":source_type},
            "context":{"summary":asset.summary,"themes":list(asset.detected_themes or ())}}
