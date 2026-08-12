"""Download, validate, inspect, posterize and persist generated video media."""
from __future__ import annotations
import hashlib,json,mimetypes,os,subprocess
from pathlib import Path
from uuid import uuid4
import requests
from app.database import get_db_connection
from app.models.creator_intent import CreatorIntent
from app.services.ai_import_workflow_service import AIImportWorkflowService

VIDEO_SUFFIXES={".mp4",".mov",".webm",".m4v"}
class GeneratedMediaService:
    def __init__(self,root=None,http_client=None,connection_factory=get_db_connection,import_workflow=None):
        self.root=Path(root or os.getenv("GENERATED_MEDIA_ROOT","data/generated_media")); self.http=http_client or requests; self.connection_factory=connection_factory; self.import_workflow=import_workflow or AIImportWorkflowService()
    def ingest_video(self,*,url,creator_profile_id,account_id,provider_id,lineage,generation_metadata):
        media_id=uuid4(); folder=self.root/str(media_id); folder.mkdir(parents=True,exist_ok=True)
        suffix=Path(url.split("?",1)[0]).suffix.lower(); suffix=suffix if suffix in VIDEO_SUFFIXES else ".mp4"; target=folder/f"video{suffix}"
        response=self.http.get(url,stream=True,timeout=180); response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_content(1024*1024):
                if chunk: output.write(chunk)
        if target.stat().st_size<=0: raise ValueError("Downloaded provider video is empty.")
        metadata=self.probe(target); duration=float(metadata.get("duration") or 0)
        if duration<=0: raise ValueError("Downloaded provider video has no readable duration.")
        poster=folder/"poster.jpg"; poster_path=None
        try:
            subprocess.run(["ffmpeg","-y","-ss","0.1","-i",str(target),"-frames:v","1",str(poster)],check=True,capture_output=True,timeout=60); poster_path=str(poster)
        except (OSError,subprocess.SubprocessError):
            try:
                import cv2
                capture=cv2.VideoCapture(str(target)); ok,frame=capture.read(); capture.release()
                if ok and cv2.imwrite(str(poster),frame): poster_path=str(poster)
            except Exception: pass
        with self.connection_factory() as conn,conn.cursor() as cur:
            cur.execute("""INSERT INTO public.generated_media(media_id,creator_profile_id,account_id,media_type,media_path,poster_path,duration_seconds,width,height,provider_id,source_lineage,generation_metadata)
              VALUES(%s,%s,%s,'video',%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING *""",
              (media_id,creator_profile_id,account_id,str(target),poster_path,duration,metadata.get("width"),metadata.get("height"),provider_id,json.dumps(lineage),json.dumps(generation_metadata)))
            record=dict(cur.fetchone())
        concept = dict(generation_metadata.get("concept") or {})
        canonical_title = str(concept.get("title") or "").strip() or None
        imported=self.import_workflow.import_asset(media_path=target,upload_intent="teaser_video",creator_profile_id=creator_profile_id,creator_intent=CreatorIntent.create("single_asset",legacy_upload_intent="teaser_video",metadata={"source":"video_studio","generated_media_id":str(media_id),"lineage":lineage,"canonical_media_title":canonical_title}),original_filename=target.name,create_product_draft=False,provider_upload_enabled=False,is_test=False,import_session_id=f"video-studio:{media_id}")
        asset_id=getattr(imported,"content_id",None)
        if not getattr(imported,"success",False) or asset_id is None: raise RuntimeError("Generated video was persisted but Asset registration failed.")
        asset = getattr(imported, "asset", None) or self.import_workflow.assets.get_by_id(int(asset_id))
        if asset is not None and canonical_title:
            media_metadata = dict(getattr(asset, "media_metadata", None) or {})
            media_metadata["canonical_media_title"] = canonical_title
            media_metadata["video_studio"] = {
                **dict(media_metadata.get("video_studio") or {}),
                "generated_media_id": str(media_id),
                "session_id": str(lineage.get("session_id") or "") or None,
                "concept_title_source": "selected_concept.title",
            }
            self.import_workflow.assets.update_media_metadata(int(asset_id), media_metadata)
        record["asset_id"]=int(asset_id); return record
    @staticmethod
    def probe(path):
        try:
            result=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(path)],check=True,capture_output=True,text=True,timeout=30)
        except (OSError,subprocess.SubprocessError):
            try:
                import cv2
                capture=cv2.VideoCapture(str(path)); width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)); height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)); fps=float(capture.get(cv2.CAP_PROP_FPS)); frames=float(capture.get(cv2.CAP_PROP_FRAME_COUNT)); capture.release()
                if width<=0 or height<=0 or fps<=0 or frames<=0: raise ValueError
                return {"duration":frames/fps,"width":width,"height":height,"codec":None,"frame_rate":fps,"has_audio":None,"sha256":GeneratedMediaService._hash(path),"probe":"opencv_fallback"}
            except Exception as error: raise ValueError("No installed media probe could validate the generated video.") from error
        raw=json.loads(result.stdout); video=next((v for v in raw.get("streams",[]) if v.get("codec_type")=="video"),{})
        return {"duration":float(raw.get("format",{}).get("duration") or 0),"width":video.get("width"),"height":video.get("height"),"codec":video.get("codec_name"),"frame_rate":video.get("r_frame_rate"),"has_audio":any(v.get("codec_type")=="audio" for v in raw.get("streams",[])),"sha256":GeneratedMediaService._hash(path),"probe":"ffprobe"}
    @staticmethod
    def _hash(path):
        digest=hashlib.sha256()
        with Path(path).open("rb") as stream:
            for block in iter(lambda:stream.read(1024*1024),b""): digest.update(block)
        return digest.hexdigest()
    def get(self,media_id,creator_profile_id):
        with self.connection_factory() as conn,conn.cursor() as cur:
            cur.execute("SELECT * FROM public.generated_media WHERE media_id=%s AND creator_profile_id=%s",(media_id,creator_profile_id)); row=cur.fetchone(); return dict(row) if row else None
