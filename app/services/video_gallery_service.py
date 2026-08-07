"""Operator-facing projection of canonical completed Video Studio outputs."""
from app.repositories.video_studio_repository import VideoStudioRepository


class VideoGalleryService:
    def __init__(self, repository=None): self.repository=repository or VideoStudioRepository()

    @staticmethod
    def project(row):
        concept=row.get("selected_concept") or {}
        settings=row.get("settings") or {}
        snapshot=row.get("source_snapshot") or {}
        lineage=row.get("media_lineage") or row.get("source_lineage") or {}
        media_id=str(row["final_generated_media_id"])
        source_type=row.get("source_type") or "unknown"
        labels={"generation":"Generation Library image","photoshoot_shot":"Photoshoot image","asset":"Asset Library image","edit_result":"Edit Studio result","generated_video":"Generated video","upload":"Uploaded image"}
        source_label=snapshot.get("label") or snapshot.get("file_name") or snapshot.get("source_label") or labels.get(source_type,source_type.replace("_"," ").title())
        capability=row.get("provider_capability") or {}
        return {
            "generatedMediaId":media_id,"sessionId":str(row["session_id"]),
            "title":concept.get("title") or "Generated video","conceptSummary":concept.get("experience_summary") or concept.get("overall_theme"),
            "posterUrl":f"/api/v1/video-studio/media/{media_id}/poster","mediaUrl":f"/api/v1/video-studio/media/{media_id}",
            "duration":float(row.get("duration_seconds") or settings.get("desired_runtime") or 0),"resolution":settings.get("resolution"),
            "width":row.get("width"),"height":row.get("height"),"aspectRatio":settings.get("aspect_ratio"),"hasAudio":bool(settings.get("generate_audio")),
            "providerId":row.get("provider_id"),"providerModel":capability.get("display_name") or row.get("provider_id"),
            "createdAt":row.get("media_created_at") or row.get("created_at"),"sourceType":source_type,"sourceId":row.get("source_id"),
            "sourceLabel":source_label,"sourcePreviewUrl":snapshot.get("preview_url") or snapshot.get("previewUrl"),
            "completionStatus":"COMPLETE","assetState":"IN_ASSET_LIBRARY" if row.get("final_asset_id") else "NOT_REGISTERED",
            "finalAssetId":row.get("final_asset_id"),"lineage":lineage,"extensionAvailable":bool(capability.get("video_extension")),
            "alternateGenerationAvailable":True,
        }

    def list(self, creator_profile_id, **filters):
        rows,total=self.repository.list_gallery(creator_profile_id,**filters)
        return [self.project(row) for row in rows],total

    def get(self, media_id, creator_profile_id):
        row=self.repository.get_gallery_item(media_id,creator_profile_id)
        return self.project(row) if row else None
