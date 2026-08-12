import copy
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationJob, GenerationRequest, GenerationResult
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_recipe_capture_service import GenerationRecipeCaptureService


class MemoryRecipeRepository:
    def __init__(self, fail_create=False):
        self.fail_create=fail_create; self.recipes=[]; self.transitions=[]; self.outputs=[]
    def create(self, recipe):
        if self.fail_create: raise RuntimeError("recipe persistence unavailable")
        self.recipes.append(recipe); return recipe
    def transition_execution(self, recipe_id, status, **values): self.transitions.append((str(recipe_id),status,values))
    def associate_output(self, recipe_id, **values): self.outputs.append((str(recipe_id),values))


class FakeResponse:
    def __init__(self, payload, status_code=200): self.payload=payload; self.status_code=status_code; self.text=str(payload)
    def json(self): return self.payload
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(self, fail=False, status_code=200): self.posts=[]; self.fail=fail; self.status_code=status_code; self.counter=0
    def post(self, url, **kwargs):
        self.posts.append((url,kwargs))
        if self.fail: raise TimeoutError("connection closed")
        self.counter+=1; return FakeResponse({"data":{"id":f"provider-{self.counter}"}},self.status_code)
    def get(self, url, **kwargs): return FakeResponse({"data":{"status":"completed","outputs":[f"https://cdn.test/{self.counter}.png"]}})


class CountingSeedream(Seedream50ProProvider):
    def __init__(self, **kwargs): super().__init__(**kwargs); self.build_count=0
    def build_payload(self, request): self.build_count+=1; return super().build_payload(request)


def request(*, image_count=1):
    return GenerationRequest(
        request_id="request-1",creator_profile_id=2,prompt_plan_id="plan-1",
        prompt_text="planned explicit portrait",reference_asset_id=93,
        reference_asset_path="https://refs.test/identity.png?signature=secret",
        provider_id="seedream_5_0_pro",generation_type="image_to_image",media_type="image",
        image_count=image_count,metadata={"generation_job_id":"job-1","workflow_type":"photoshoot",
        "creative_mode":"explicit","render_policy":"PHOTOSHOOT_EXPLICIT",
        "canonical_reference_image_url":"https://refs.test/identity.png?token=secret",
        "photoshoot_continuity_reference_image_url":"https://refs.test/continuity.png?signature=secret",
        "reference_image_url":"https://refs.test/continuity.png?signature=secret"},
    )


def provider(repository, http=None):
    return CountingSeedream(api_key="test",http_client=http or FakeHttp(),poll_interval_seconds=0,
        max_poll_attempts=1,recipe_capture_service=GenerationRecipeCaptureService(repository))


def test_final_prompt_payload_identity_build_once_order_and_no_mutation():
    repository=MemoryRecipeRepository(); http=FakeHttp(); item=provider(repository,http)
    original_build=item.build_payload
    captured_payloads=[]
    def observed(req):
        value=original_build(req); captured_payloads.append(copy.deepcopy(value)); return value
    item.build_payload=observed
    submitted=item.submit_generation(request())
    recipe=repository.recipes[0]; sent=http.posts[0][1]["json"]
    assert item.build_count == 1
    assert recipe.final_prompt == sent["prompt"] == captured_payloads[0]["prompt"]
    assert "CANONICAL AVA FACIAL NATURALISM" in recipe.final_prompt
    assert "Image 1 controls identity" in recipe.final_prompt
    assert sent == captured_payloads[0]
    assert [ref.role for ref in recipe.references] == ["CANONICAL_IDENTITY","PHOTOSHOOT_CONTINUITY"]
    assert [ref.position for ref in recipe.references] == [1,2]
    assert recipe.sanitized_provider_payload["images"] == ["recipe-reference://1","recipe-reference://2"]
    assert submitted.generation_recipe_id == str(recipe.recipe_id)


def test_sanitization_removes_secrets_and_signed_reference_urls():
    repository=MemoryRecipeRepository(); service=GenerationRecipeCaptureService(repository)
    item=provider(repository)
    payload={"prompt":"literal","images":["https://x.test/a.png?token=secret"],
             "authorization":"Bearer secret","nested":{"api_key":"secret","url":"https://x.test/b?signature=s"}}
    snapshot=copy.deepcopy(payload); recipe=service.capture(request=request(),provider=item,final_payload=payload)
    assert payload == snapshot
    assert recipe.final_prompt == "literal"
    assert recipe.sanitized_provider_payload["authorization"] == "[REDACTED]"
    assert recipe.sanitized_provider_payload["nested"]["api_key"] == "[REDACTED]"
    assert recipe.sanitized_provider_payload["nested"]["url"] == "https://x.test/b"
    assert "secret" not in str(recipe.sanitized_provider_payload)


def test_recipe_failure_closes_before_http_submission():
    repository=MemoryRecipeRepository(fail_create=True); http=FakeHttp(); item=provider(repository,http)
    with pytest.raises(RuntimeError,match="recipe persistence unavailable"): item.submit_generation(request())
    assert http.posts == []


def test_provider_transport_failure_retains_recipe_and_records_ambiguity():
    repository=MemoryRecipeRepository(); http=FakeHttp(fail=True); item=provider(repository,http)
    with pytest.raises(Exception): item.submit_generation(request())
    assert len(repository.recipes)==1
    assert [status for _,status,_ in repository.transitions][-1] == "SUBMISSION_AMBIGUOUS"


def test_provider_rejection_retains_recipe_and_records_failure():
    repository=MemoryRecipeRepository(); http=FakeHttp(status_code=500); item=provider(repository,http)
    with pytest.raises(Exception): item.submit_generation(request())
    assert len(repository.recipes)==1
    assert [status for _,status,_ in repository.transitions][-1] == "SUBMISSION_REJECTED"


def test_multi_image_execution_creates_one_recipe_per_submission():
    repository=MemoryRecipeRepository(); http=FakeHttp(); item=provider(repository,http)
    result=item.execute_with_progress(request(image_count=3))
    assert len(repository.recipes)==3
    assert [recipe.submission_index for recipe in repository.recipes] == [0,1,2]
    assert len(http.posts)==3
    assert tuple(result.generation_metadata["output_generation_recipe_ids"]) == tuple(str(x.recipe_id) for x in repository.recipes)


class ArchiveStub:
    def materialize_generation(self, record): return record
    def list_records(self): return ()
    def content_paths(self): return {"generation_active":Path("data/generation_library")}


class CaptureStub:
    def __init__(self): self.calls=[]
    def associate_output(self, recipe_id, **values): self.calls.append((recipe_id,values))


def test_generation_library_links_new_recipe_and_loads_legacy_null():
    recipe_id=str(uuid4()); capture=CaptureStub()
    with tempfile.TemporaryDirectory() as directory:
        service=GenerationLibraryService(storage_dir=directory,archive_service=ArchiveStub(),recipe_capture_service=capture)
        result=GenerationResult(result_id="result-1",request_id="request-1",job_id="job-1",provider_id="seedream_5_0_pro",status="succeeded",generation_metadata={"output_generation_recipe_ids":[recipe_id]},output_references=(str(Path(directory)/"output.png"),))
        Path(result.output_references[0]).write_bytes(b"image")
        job=GenerationJob(job_id="job-1",request=request(),status="succeeded",result=result)
        records=service.sync_job(job)
        assert records[0].generation_recipe_id == recipe_id
        assert capture.calls[0][0] == recipe_id
        legacy=service._record_from_dict({**records[0].__dict__,"generation_recipe_id":None})
        assert legacy.generation_recipe_id is None
