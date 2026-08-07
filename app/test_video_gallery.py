from datetime import datetime,timezone
from uuid import uuid4
from app.services.video_gallery_service import VideoGalleryService


def gallery_row(**changes):
    media_id=uuid4(); session_id=uuid4()
    value={"final_generated_media_id":media_id,"session_id":session_id,"selected_concept":{"title":"Quiet Light","experience_summary":"A calm cinematic scene."},"settings":{"desired_runtime":15,"resolution":"720p","aspect_ratio":"9:16","generate_audio":True},"source_snapshot":{"label":"Photoshoot · Shot 7"},"source_lineage":{"photoshoot_session_id":"p1"},"media_lineage":{"session_id":str(session_id)},"source_type":"photoshoot_shot","source_id":"shot-7","duration_seconds":15,"width":720,"height":1280,"provider_id":"wavespeed_seedance_2_0","provider_capability":{"display_name":"Seedance 2.0 (WaveSpeed)","video_extension":True},"media_created_at":datetime.now(timezone.utc),"final_asset_id":42}
    value.update(changes); return value

class Repo:
    def __init__(self,rows): self.rows=rows; self.calls=[]
    def list_gallery(self,creator_profile_id,**filters): self.calls.append((creator_profile_id,filters)); return self.rows,len(self.rows)
    def get_gallery_item(self,media_id,creator_profile_id): return next((r for r in self.rows if str(r["final_generated_media_id"])==str(media_id)),None)

def test_completed_logical_video_projection_includes_lineage_and_asset_state():
    row=gallery_row(); service=VideoGalleryService(Repo([row])); items,total=service.list(7,page=1,page_size=24,sort="newest")
    assert total==1 and items[0]["generatedMediaId"]==str(row["final_generated_media_id"])
    assert items[0]["sourceLabel"]=="Photoshoot · Shot 7" and items[0]["assetState"]=="IN_ASSET_LIBRARY"
    assert items[0]["posterUrl"].endswith("/poster") and items[0]["extensionAvailable"] is True

def test_gallery_pagination_sort_and_creator_are_forwarded_to_authority():
    repo=Repo([]); VideoGalleryService(repo).list(9,page=2,page_size=10,sort="oldest",provider_id="provider",search="quiet")
    assert repo.calls==[(9,{"page":2,"page_size":10,"sort":"oldest","provider_id":"provider","search":"quiet"})]

def test_detail_lookup_is_scoped_and_missing_returns_none():
    row=gallery_row(); repo=Repo([row]); service=VideoGalleryService(repo)
    assert service.get(row["final_generated_media_id"],3)["sessionId"]==str(row["session_id"])
    assert service.get(uuid4(),3) is None
