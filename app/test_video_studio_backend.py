from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.models.generation_engine import GenerationRequest
from app.models.video_studio import SEEDANCE_20_CAPABILITY,VideoProviderCapabilityService
from app.providers.generation.seedance_video_provider import Seedance20VideoProvider
from app.services.video_execution_planner import balanced_durations,VideoExecutionPlanner
from app.services.video_concept_services import validate_video_concept,VideoConceptDirectorService
from app.services.generated_media_service import GeneratedMediaService
from app.api.video_studio import Settings
from app.api.video_studio import _raise_video_error
from fastapi import HTTPException
from app.services.video_source_resolver import VideoSourceResolver


def request(kind="image_to_video",**metadata):
    return GenerationRequest(request_id="r",creator_profile_id=1,prompt_plan_id="p",prompt_text="A coherent cinematic movement",reference_asset_id=1,reference_asset_path="https://example.test/source.jpg",provider_id="wavespeed_seedance_2_0",generation_type=kind,media_type="video",metadata={"duration":5,**metadata})

def test_seedance_capability_contract():
    capability=VideoProviderCapabilityService().require("wavespeed_seedance_2_0")
    assert capability.min_native_duration==4 and capability.max_native_duration==15
    assert capability.video_extension and capability.audio_on_extension

def test_new_video_session_api_defaults_to_vertical_aspect_ratio():
    assert Settings(desired_runtime=15).aspect_ratio == "9:16"

def test_known_concept_failure_maps_to_recoverable_api_error():
    with pytest.raises(HTTPException) as raised:
        _raise_video_error(ValueError("timeline malformed"),"concepts")
    assert raised.value.status_code==502
    assert "preserved for retry" in raised.value.detail

def test_generation_source_resolves_owned_readable_image(tmp_path):
    image=tmp_path/"generation.png"; image.write_bytes(b"png")
    record=type("Record",(),{"image_id":"generated-1","creator_profile_id":2,"output_reference":str(image),"generation_result_id":"result-1","updated_at":None,"imported_asset_id":None,"photoshoot_session_id":None,"photoshoot_request_id":None,"creative_mode":"premium","prompt_text":"A source"})()
    library=type("Library",(),{"get":lambda self,image_id:record})()
    resolver=VideoSourceResolver(asset_repository=object(),generation_library=library)
    source=resolver.resolve(source_type="generation",source_id="generated-1",creator_profile_id=2)
    assert source["source_media_type"]=="image"
    assert source["physical_path"]==str(image)
    assert source["lineage"]["generation_id"]=="generated-1"

def test_seedance_image_to_video_payload():
    provider=Seedance20VideoProvider(api_key="test")
    payload=provider.build_payload(request(aspect_ratio="9:16",resolution="1080p",generate_audio=False))
    assert payload=={"prompt":"A coherent cinematic movement","duration":5,"resolution":"1080p","generate_audio":False,"enable_web_search":False,"image":"https://example.test/source.jpg","aspect_ratio":"9:16"}

def test_seedance_extension_payload_omits_aspect_ratio():
    provider=Seedance20VideoProvider(api_key="test")
    payload=provider.build_payload(request("video_extend",input_video_url="https://example.test/video.mp4",aspect_ratio="9:16",generate_audio=True))
    assert payload["video"].endswith("video.mp4") and "image" not in payload and "aspect_ratio" not in payload

@pytest.mark.parametrize(("runtime","expected"),[(5,(5,)),(10,(10,)),(15,(15,)),(17,(9,8)),(30,(15,15)),(45,(15,15,15)),(60,(15,15,15,15))])
def test_balanced_runtime_segmentation(runtime,expected):
    assert balanced_durations(runtime,4,15)==expected

def sample_concept(runtime=17):
    return {"title":"Arc","overall_theme":"Calm","experience_summary":"One evolving scene","tone":"cinematic","viewer_experience":"intimate","pacing":"gradual","narrative_arc":"settles then connects","output_intent":"continuous","requested_runtime":runtime,"timeline":[{"start_second":0,"end_second":7,"creative_beat":"settles"},{"start_second":7,"end_second":runtime,"creative_beat":"connects and ends"}]}

def test_execution_plan_maps_complete_timeline():
    plan=VideoExecutionPlanner().plan(sample_concept(),asdict(SEEDANCE_20_CAPABILITY),session_id="s",run_id="r")
    assert [s["planned_duration"] for s in plan["segments"]]==[9,8]
    assert [s["generation_type"] for s in plan["segments"]]==["image_to_video","video_extend"]

def test_manual_extension_plan_starts_with_video_extend():
    plan=VideoExecutionPlanner().plan(sample_concept(),asdict(SEEDANCE_20_CAPABILITY),session_id="s",run_id="r",source_media_type="video")
    assert all(segment["generation_type"]=="video_extend" for segment in plan["segments"])

def test_concept_contract_rejects_gap():
    concept=sample_concept(); concept["timeline"][1]["start_second"]=8
    with pytest.raises(ValueError,match="gap"): validate_video_concept(concept,17)

def test_mocked_grok_director_complete_timeline():
    raw=sample_concept(15)
    director=VideoConceptDirectorService(runner=lambda prompt,image:{"concepts":[dict(raw) for _ in range(4)]})
    concepts=director.create(intelligence={"intelligence_id":"i"},settings={"desired_runtime":15,"settings_version":2},capability=asdict(SEEDANCE_20_CAPABILITY))
    assert len(concepts)==4 and all(c["timeline"][-1]["end_second"]==15 for c in concepts)

def test_video_probe_falls_back_without_system_ffprobe(tmp_path):
    import cv2, numpy as np
    path=tmp_path/"sample.mp4"; writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"mp4v"),10,(32,24))
    for _ in range(10): writer.write(np.zeros((24,32,3),dtype=np.uint8))
    writer.release(); metadata=GeneratedMediaService.probe(path)
    assert metadata["duration"]>0 and metadata["width"]==32 and metadata["height"]==24

def test_generated_video_asset_reuses_selected_concept_title(monkeypatch, tmp_path):
    class Response:
        def raise_for_status(self): pass
        def iter_content(self, _size): return (b"video",)
    class Cursor:
        def execute(self, *_args): pass
        def fetchone(self): return {"media_id": "media-1"}
        def __enter__(self): return self
        def __exit__(self, *_args): pass
    class Connection:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self, *_args): pass
    class Assets:
        def __init__(self): self.updated = None
        def get_by_id(self, _asset_id): return SimpleNamespace(media_metadata={"media_type": "video"})
        def update_media_metadata(self, asset_id, metadata): self.updated = (asset_id, metadata)
    assets = Assets()
    workflow = SimpleNamespace(
        assets=assets,
        import_asset=lambda **_kwargs: SimpleNamespace(success=True, content_id=88, asset=None),
    )
    service = GeneratedMediaService(
        root=tmp_path, http_client=SimpleNamespace(get=lambda *_args, **_kwargs: Response()),
        connection_factory=lambda: Connection(), import_workflow=workflow,
    )
    monkeypatch.setattr(service, "probe", lambda _path: {"duration": 15, "width": 720, "height": 1280})
    monkeypatch.setattr("app.services.generated_media_service.subprocess.run", lambda *_args, **_kwargs: None)

    result = service.ingest_video(
        url="https://provider.test/output.mp4", creator_profile_id=7, account_id=9,
        provider_id="seedance", lineage={"session_id": "session-1"},
        generation_metadata={"concept": {"title": "Steamy Shower Escape"}},
    )

    assert result["asset_id"] == 88
    assert assets.updated[0] == 88
    assert assets.updated[1]["canonical_media_title"] == "Steamy Shower Escape"
    assert assets.updated[1]["video_studio"]["concept_title_source"] == "selected_concept.title"
