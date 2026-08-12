from __future__ import annotations

import copy
import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.api.regeneration import RegenerationPromoteRequest, RegenerationStartRequest
from app.models.generation_engine import (
    GenerationJob, GenerationRequest, GenerationResult, GenerationStatus,
    ProviderPromptState,
)
from app.models.generation_recipe import (
    GenerationRecipe, GenerationRecipeExecution, GenerationRecipeOutput,
    GenerationRecipeReference,
)
from app.models.regeneration import RegenerationEligibility, RegenerationResult, RegenerationRun
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.repositories.generation_recipe_repository import GenerationRecipeRepository
from app.services.regeneration_eligibility_service import RegenerationEligibilityService
from app.services.regeneration_service import RegenerationIneligible, RegenerationService
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_engine_service import GenerationEngineService


def recipe(**updates):
    recipe_id = updates.pop("recipe_id", uuid4())
    prompt = updates.pop("final_prompt", "literal final provider prompt\n\nEXISTING LOCK")
    values = dict(
        recipe_id=recipe_id, schema_version="generation_recipe_v1", generation_job_id="original-job",
        generation_request_id="original-request", prompt_plan_id="original-plan", submission_index=0,
        source_workflow="premium", workflow_origin="explicit_tags", provider_id="seedream_5_0_pro",
        provider_family="wavespeed", provider_adapter="app.providers.generation.seedream_provider.Seedream50ProProvider",
        provider_adapter_version=None,
        provider_endpoint="https://api.wavespeed.ai/api/v3/bytedance/seedream-v5.0-pro/edit",
        provider_model="seedream-v5.0-pro/edit", provider_model_revision=None,
        generation_type="image_to_image", media_type="image", planned_prompt="planned",
        final_prompt=prompt, final_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        creative_mode="explicit", render_policy="CONTENT_EXPLICIT", render_policy_version=None,
        normalized_settings={"output_format": "png"}, output_format="png", width=None, height=None,
        aspect_ratio=None, resolution=None, seed=None, seed_policy="OMITTED_PROVIDER_RANDOM",
        sanitized_provider_payload={"prompt": prompt, "images": ["recipe-reference://1"], "output_format": "png"},
        sanitized_payload_sha256="payload-hash",
        references=(GenerationRecipeReference(uuid4(), recipe_id, 1, "CANONICAL_IDENTITY",
                                              "CANONICAL_ASSET", asset_id=93, media_type="image",
                                              provider_reference_kind="images"),),
    )
    values.update(updates)
    return GenerationRecipe(**values)


class MemoryRecipes:
    def __init__(self, item, *, execution="SUCCEEDED", linked_image="source-image"):
        self.items = {str(item.recipe_id): item}
        self.executions = {str(item.recipe_id): GenerationRecipeExecution(item.recipe_id, execution, "provider-old")}
        self.output_rows = {str(item.recipe_id): [GenerationRecipeOutput(uuid4(), item.recipe_id, "old-result", linked_image, 0)]}
        self.associated = []

    def get(self, recipe_id): return self.items.get(str(recipe_id))
    def get_execution(self, recipe_id): return self.executions.get(str(recipe_id))
    def outputs(self, recipe_id): return tuple(self.output_rows.get(str(recipe_id), ()))
    def get_by_request(self, request_id, submission_index=0):
        return next((item for item in self.items.values() if item.generation_request_id == request_id), None)
    def associate_output(self, recipe_id, **values): self.associated.append((str(recipe_id), values))


class MemoryLibrary:
    def __init__(self, record): self.record = record; self.get_calls = []
    def get(self, image_id):
        self.get_calls.append(image_id)
        if image_id != self.record.image_id: raise KeyError(image_id)
        return self.record


class ProviderRegistry:
    def __init__(self, provider=None): self.provider = provider or Seedream50ProProvider(
        api_key="test", recipe_capture_service=SimpleNamespace(),
    )
    def get(self, provider_id): return self.provider if provider_id == self.provider.provider_id else None
    def require(self, provider_id):
        value = self.get(provider_id)
        if not value: raise KeyError(provider_id)
        return value


class ReferenceService:
    def __init__(self, path): self.path = str(path)
    def get_owned_reference(self, asset_id, *, creator_profile_id):
        return SimpleNamespace(asset=SimpleNamespace(original_path=self.path)) if asset_id == 93 else None


def eligibility_fixture(tmp_path, **recipe_updates):
    reference = tmp_path / "identity.png"; reference.write_bytes(b"identity")
    source_recipe = recipe(**recipe_updates)
    record = SimpleNamespace(image_id="source-image", generation_recipe_id=str(source_recipe.recipe_id),
                             creator_profile_id=7, output_reference=str(tmp_path / "source.png"))
    Path(record.output_reference).write_bytes(b"source")
    recipes = MemoryRecipes(source_recipe)
    library = MemoryLibrary(record)
    service = RegenerationEligibilityService(
        generation_library=library, recipes=recipes, references=ReferenceService(reference),
        provider_registry=ProviderRegistry(),
    )
    return service, record, source_recipe, recipes, reference


def test_valid_sfw_and_explicit_recipes_are_eligible(tmp_path):
    explicit, *_ = eligibility_fixture(tmp_path, creative_mode="explicit", render_policy="CONTENT_EXPLICIT")
    assert explicit.inspect("source-image").can_regenerate
    sfw, *_ = eligibility_fixture(tmp_path, creative_mode="premium_teaser", render_policy="CONTENT_SPICY")
    assert sfw.inspect("source-image").can_regenerate
    promoted, *_ = eligibility_fixture(tmp_path, source_workflow="REGENERATION_STUDIO")
    assert promoted.inspect("source-image").can_regenerate


def test_recipe_repository_insert_contract_includes_regeneration_lineage():
    source = recipe()
    item = recipe(source_workflow="REGENERATION_STUDIO", source_generated_image_id="source-image",
                  source_recipe_id=source.recipe_id, regeneration_operation_id=uuid4())
    calls = []
    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, params=()):
            assert query.count("%s") == len(params)
            calls.append((query, params))
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
    GenerationRecipeRepository(connection_factory=lambda: Connection()).create(item)
    insert = calls[0]
    assert item.source_generated_image_id in insert[1]
    assert item.source_recipe_id in insert[1]
    assert item.regeneration_operation_id in insert[1]


@pytest.mark.parametrize("case,code", [
    ("legacy", "RECIPE_NOT_CAPTURED"), ("missing", "RECIPE_NOT_FOUND"),
    ("failed", "ORIGINAL_EXECUTION_NOT_SUCCESSFUL"), ("unlinked", "OUTPUT_LINK_MISSING"),
    ("schema", "UNSUPPORTED_RECIPE_SCHEMA"), ("reference", "REFERENCE_UNAVAILABLE"),
])
def test_ineligible_reasons_are_structured(tmp_path, case, code):
    service, record, source_recipe, recipes, reference = eligibility_fixture(tmp_path)
    if case == "legacy": record.generation_recipe_id = None
    elif case == "missing": recipes.items.clear()
    elif case == "failed": recipes.executions[str(source_recipe.recipe_id)] = GenerationRecipeExecution(source_recipe.recipe_id, "FAILED")
    elif case == "unlinked": recipes.output_rows[str(source_recipe.recipe_id)] = []
    elif case == "schema": recipes.items[str(source_recipe.recipe_id)] = replace(source_recipe, schema_version="future")
    elif case == "reference": reference.unlink()
    result = service.inspect("source-image")
    assert not result.can_regenerate and result.reason_code == code and result.reason


def test_deterministic_edit_workflow_and_provider_mismatch_are_ineligible(tmp_path):
    service, *_ = eligibility_fixture(tmp_path, source_workflow="edit")
    assert service.inspect("source-image").reason_code == "UNSUPPORTED_WORKFLOW"
    service, *_ = eligibility_fixture(tmp_path, provider_model="different-model")
    assert service.inspect("source-image").reason_code == "PROVIDER_INCOMPATIBLE"
    service, *_ = eligibility_fixture(tmp_path, normalized_settings={"unsupported": True})
    assert service.inspect("source-image").reason_code == "SETTINGS_REPLAY_UNSUPPORTED"


def test_eligibility_is_creator_scoped(tmp_path):
    service, *_ = eligibility_fixture(tmp_path)
    assert service.inspect("source-image", creator_profile_id=999).reason_code == "SOURCE_NOT_OWNED"


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_public_request_accepts_only_integer_counts_one_through_five(count):
    assert RegenerationStartRequest(source_generated_image_id="image", count=count).count == count


@pytest.mark.parametrize("count", [0, -1, 6, 1.5, "2", True, None])
def test_public_request_rejects_invalid_counts(count):
    with pytest.raises(ValidationError):
        RegenerationStartRequest(source_generated_image_id="image", count=count)


def test_public_request_forbids_all_trusted_replay_fields():
    for field in ("prompt", "provider", "model", "reference_asset_id", "source_recipe_id", "prompt_state"):
        with pytest.raises(ValidationError):
            RegenerationStartRequest(source_generated_image_id="image", count=1, **{field: "injected"})


def test_public_promotion_accepts_only_canonical_result_ids():
    assert RegenerationPromoteRequest(result_ids=["result-1"]).result_ids == ["result-1"]
    with pytest.raises(ValidationError):
        RegenerationPromoteRequest(result_ids=["result-1"], media_path="injected")


def test_trusted_replay_is_byte_exact_and_does_not_add_locks_or_source_image(tmp_path):
    eligibility, record, source_recipe, recipes, reference = eligibility_fixture(tmp_path)
    service = RegenerationService(eligibility=eligibility, recipes=recipes, repository=SimpleNamespace())
    operation = SimpleNamespace(operation_id=uuid4(), creator_profile_id=7)
    resolved = eligibility.resolve_references(source_recipe, record.creator_profile_id)
    request = service._build_request(operation, 1, record, source_recipe, resolved)
    request = replace(request, metadata={
        **request.metadata, "reference_image_url": "https://safe.test/id.png",
    })
    provider = Seedream50ProProvider(
        api_key="test", hosted_reference_service=SimpleNamespace(resolve=lambda **kwargs: "https://safe.test/id.png"),
        recipe_capture_service=SimpleNamespace(),
    )
    payload = provider.build_payload(request)
    assert request.prompt_state == ProviderPromptState.FINAL_PROVIDER_RENDERED.value
    assert payload["prompt"] == source_recipe.final_prompt
    assert payload["prompt"].count("EXISTING LOCK") == 1
    assert request.reference_asset_path == str(reference)
    assert record.output_reference not in payload["images"]
    assert "source-image" not in payload["images"]
    assert "seed" not in payload
    assert request.metadata["regeneration_seed_policy"] == "OMITTED_PROVIDER_RANDOM"


def test_trusted_regeneration_prompt_state_survives_rehydration_without_rerendering(tmp_path):
    eligibility, record, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    regeneration = RegenerationService(
        eligibility=eligibility, recipes=recipes, repository=SimpleNamespace(),
    )
    request = regeneration._build_request(
        SimpleNamespace(operation_id=uuid4(), creator_profile_id=7), 1,
        record, source_recipe,
        eligibility.resolve_references(source_recipe, record.creator_profile_id),
    )
    engine = GenerationEngineService(storage_dir=tmp_path / "engine")
    queued = engine.enqueue(request)

    rehydrated = GenerationEngineService(storage_dir=tmp_path / "engine").get_job(queued.job_id)
    assert rehydrated.request.prompt_state == ProviderPromptState.FINAL_PROVIDER_RENDERED.value

    provider = Seedream50ProProvider(api_key="test", recipe_capture_service=SimpleNamespace())
    rendered = provider._render_prompt_text(rehydrated.request)
    assert rendered == source_recipe.final_prompt
    assert rendered.count("EXISTING LOCK") == 1


def test_untrusted_final_marker_cannot_bypass_rendering():
    request = GenerationRequest(
        request_id="x", creator_profile_id=1, prompt_plan_id="p", prompt_text="plain",
        reference_asset_id=93, reference_asset_path="https://safe.test/id.png",
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
        prompt_state=ProviderPromptState.FINAL_PROVIDER_RENDERED.value,
        metadata={"render_policy": "CONTENT_STANDARD"},
    )
    assert Seedream50ProProvider(api_key="test", recipe_capture_service=SimpleNamespace()).build_payload(request)["prompt"] != "plain"


def test_photoshoot_reference_order_is_preserved(tmp_path):
    identity = tmp_path / "identity.png"; identity.write_bytes(b"identity")
    continuity = tmp_path / "continuity.png"; continuity.write_bytes(b"continuity")
    source_recipe = recipe(source_workflow="photoshoot", render_policy="PHOTOSHOOT_EXPLICIT")
    second = replace(source_recipe.references[0], recipe_reference_id=uuid4(), position=2,
                     role="PHOTOSHOOT_CONTINUITY", source_type="GENERATED_IMAGE",
                     asset_id=None, generated_image_id="continuity-image", source_id="continuity-image")
    source_recipe = replace(source_recipe, references=(source_recipe.references[0], second))
    source = SimpleNamespace(image_id="source-image", generation_recipe_id=str(source_recipe.recipe_id),
                             creator_profile_id=7, output_reference=str(tmp_path / "source.png"))
    continuity_record = SimpleNamespace(image_id="continuity-image", output_reference=str(continuity))
    class Library:
        def get(self, image_id): return source if image_id == "source-image" else continuity_record
    recipes = MemoryRecipes(source_recipe)
    service = RegenerationEligibilityService(generation_library=Library(), recipes=recipes,
        references=ReferenceService(identity), provider_registry=ProviderRegistry())
    resolved = service.resolve_references(source_recipe, 7)
    assert [item.role for item, _ in resolved] == ["CANONICAL_IDENTITY", "PHOTOSHOOT_CONTINUITY"]
    request = RegenerationService(eligibility=service, recipes=recipes, repository=SimpleNamespace())._build_request(
        SimpleNamespace(operation_id=uuid4()), 1, source, source_recipe, resolved)
    assert request.reference_asset_path == str(identity)
    assert request.metadata["photoshoot_continuity_reference_image_url"] == str(continuity)


class MemoryWorkspace:
    def __init__(self): self.runs = {}; self.rows = {}
    def ensure_run(self, **values):
        op = values["operation_id"]
        self.runs.setdefault(op, RegenerationRun(status="QUEUED", **values))
        self.rows.setdefault(op, [RegenerationResult(uuid4(), op, i, "PENDING") for i in range(1, values["requested_count"] + 1)])
        return self.runs[op]
    def get_run(self, op, creator_profile_id=None): return self.runs.get(op)
    def results(self, op): return tuple(self.rows[op])
    def update_run_status(self, op, status): self.runs[op] = replace(self.runs[op], status=status); return self.runs[op]
    def start_result(self, op, i): return self._set(op, i, status="RUNNING")
    def set_result_job(self, op, i, job): return self._set(op, i, generation_job_id=job)
    def succeed_result(self, op, i, **values): return self._set(op, i, status="SUCCEEDED", **values)
    def fail_result(self, op, i, error, *, code="GENERATION_FAILED", recipe_id=None, ambiguous=False):
        return self._set(op, i, status="SUBMISSION_AMBIGUOUS" if ambiguous else "FAILED", error_code=code, error_message=str(error), generation_recipe_id=recipe_id)
    def promote_result(self, op, result_id):
        item = next((row for row in self.rows[op] if str(row.regeneration_result_id) == str(result_id)), None)
        if item is None: raise KeyError(result_id)
        return self._set(op, item.variation_index, disposition="PROMOTED")
    def archive_result(self, op, result_id):
        item = next((row for row in self.rows[op] if str(row.regeneration_result_id) == str(result_id)), None)
        if item is None: raise KeyError(result_id)
        return self._set(op, item.variation_index, disposition="ARCHIVED")
    def restore_result(self, op, result_id):
        item = next((row for row in self.rows[op] if str(row.regeneration_result_id) == str(result_id)), None)
        if item is None: raise KeyError(result_id)
        return self._set(op, item.variation_index, disposition="PENDING_REVIEW")
    def _set(self, op, i, **values):
        index=i-1; self.rows[op][index]=replace(self.rows[op][index], **values); return self.rows[op][index]


class FakeEngine:
    def __init__(self, recipes, fail_index=None): self.recipes=recipes; self.jobs={}; self.requests=[]; self.fail_index=fail_index
    def enqueue(self, request, max_retries=0):
        self.requests.append(request); job=GenerationJob(f"job-{len(self.requests)}", replace(request, metadata={**request.metadata,"generation_job_id":f"job-{len(self.requests)}"}))
        self.jobs[job.job_id]=job; return job
    def get_job(self, job_id): return self.jobs[job_id]
    def dispatch_job(self, job_id):
        job=self.jobs[job_id]; index=len([x for x in self.jobs.values() if x.job_id <= job_id])
        if self.fail_index and job_id == f"job-{self.fail_index}":
            failed=replace(job,status="failed",failure=SimpleNamespace(reason="planned failure")); self.jobs[job_id]=failed; return failed
        rid=uuid4(); source=self.recipes.get(job.request.metadata["source_recipe_id"])
        item=replace(source,recipe_id=rid,generation_job_id=job_id,generation_request_id=job.request.request_id,
                     source_workflow="REGENERATION_STUDIO",workflow_origin="regeneration",
                     source_generated_image_id=job.request.metadata["source_generated_image_id"],
                     source_recipe_id=UUID(job.request.metadata["source_recipe_id"]),
                     regeneration_operation_id=UUID(job.request.metadata["regeneration_operation_id"]),
                     references=tuple(replace(ref,recipe_id=rid,recipe_reference_id=uuid4()) for ref in source.references))
        self.recipes.items[str(rid)]=item; self.recipes.executions[str(rid)]=GenerationRecipeExecution(rid,"SUCCEEDED",f"provider-{job_id}")
        output=Path("unused") / f"{job_id}.png"
        result=GenerationResult(f"result-{job_id}",job.request.request_id,job_id,job.request.provider_id,"succeeded",
                                generation_metadata={"output_generation_recipe_ids":(str(rid),)},output_references=(str(output),))
        done=replace(job,status="succeeded",result=result); self.jobs[job_id]=done; return done


class FakeOps:
    def __init__(self): self.progresses=[]; self.terminal=None; self.repository=SimpleNamespace(renew_lease=lambda *a,**k: True)
    def progress(self,*args,**kwargs): self.progresses.append(kwargs)
    def succeed(self,*args,**kwargs): self.terminal=("PARTIAL" if kwargs.get("partial") else "SUCCEEDED",kwargs)
    def fail(self,*args,**kwargs): self.terminal=("FAILED",kwargs)


class MediaRegenerationService(RegenerationService):
    def _materialize(self, operation_id, index, reference):
        path=self.workspace_root/str(operation_id)/f"variation_{index}.png"; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b"image"); return str(path)


def test_five_variations_are_independent_lineaged_workspace_results_and_source_is_immutable(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    workspace=MemoryWorkspace(); engine=FakeEngine(recipes); ops=FakeOps(); op=SimpleNamespace(
        operation_id=uuid4(),creator_profile_id=7,subject_id=source.image_id,progress_total=5,
        metadata={"sourceGeneratedImageId":source.image_id,"sourceRecipeId":str(source_recipe.recipe_id),"requestedCount":5})
    source_before=copy.deepcopy(source.__dict__); recipe_before=copy.deepcopy(source_recipe)
    service=MediaRegenerationService(eligibility=eligibility,repository=workspace,recipes=recipes,
                                     generation_engine=engine,workspace_root=tmp_path/"workspace")
    service.execute(op,ops,worker_id="worker")
    results=workspace.results(op.operation_id)
    assert ops.terminal[0] == "SUCCEEDED" and len(results)==5
    assert all(item.status=="SUCCEEDED" and item.disposition=="PENDING_REVIEW" for item in results)
    assert len(engine.requests)==5 and len({x.request_id for x in engine.requests})==5
    assert all(x.prompt_text==source_recipe.final_prompt and x.image_count==1 for x in engine.requests)
    assert all(x.metadata["source_generated_image_id"]==source.image_id for x in engine.requests)
    assert all(recipes.get(item.generation_recipe_id).source_recipe_id==source_recipe.recipe_id for item in results)
    assert all(recipes.get(item.generation_recipe_id).source_workflow=="REGENERATION_STUDIO" for item in results)
    assert source.__dict__==source_before and recipes.get(source_recipe.recipe_id)==recipe_before
    assert not hasattr(service, "generation_library_sync")


def test_partial_failure_retains_successful_workspace_results(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    workspace=MemoryWorkspace(); engine=FakeEngine(recipes,fail_index=3); ops=FakeOps(); op=SimpleNamespace(
        operation_id=uuid4(),creator_profile_id=7,subject_id=source.image_id,progress_total=5,
        metadata={"sourceGeneratedImageId":source.image_id,"sourceRecipeId":str(source_recipe.recipe_id),"requestedCount":5})
    MediaRegenerationService(eligibility=eligibility,repository=workspace,recipes=recipes,
        generation_engine=engine,workspace_root=tmp_path/"workspace").execute(op,ops,worker_id="worker")
    statuses=[item.status for item in workspace.results(op.operation_id)]
    assert statuses.count("SUCCEEDED")==4 and statuses.count("FAILED")==1
    assert ops.terminal[0]=="PARTIAL" and workspace.get_run(op.operation_id).status=="PARTIAL"


def test_completed_results_are_reconnectable_and_never_resubmitted(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    workspace=MemoryWorkspace(); engine=FakeEngine(recipes); ops=FakeOps(); op=SimpleNamespace(
        operation_id=uuid4(),creator_profile_id=7,subject_id=source.image_id,progress_total=1,
        metadata={"sourceGeneratedImageId":source.image_id,"sourceRecipeId":str(source_recipe.recipe_id),"requestedCount":1})
    service=MediaRegenerationService(eligibility=eligibility,repository=workspace,recipes=recipes,
        generation_engine=engine,workspace_root=tmp_path/"workspace")
    service.execute(op,ops,worker_id="worker"); first_count=len(engine.requests)
    service.execute(op,ops,worker_id="replacement-worker")
    assert len(engine.requests)==first_count==1
    assert workspace.results(op.operation_id)[0].status=="SUCCEEDED"


def test_regeneration_jobs_are_isolated_but_normal_jobs_still_sync_to_generation_library(tmp_path):
    output = tmp_path / "output.png"; output.write_bytes(b"image")
    class Archive:
        def materialize_generation(self, record): return record
        def list_records(self): return ()
        def content_paths(self): return {"generation_active": tmp_path}
    class Capture:
        def associate_output(self, *args, **kwargs): pass
    library = GenerationLibraryService(storage_dir=tmp_path / "library", archive_service=Archive(),
                                       recipe_capture_service=Capture())
    def job(source):
        request = GenerationRequest(
            request_id=f"request-{source}", creator_profile_id=7, prompt_plan_id="plan",
            prompt_text="prompt", reference_asset_id=93, reference_asset_path="reference",
            provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
            metadata={"source": source, "workflow_type": source},
        )
        result = GenerationResult(f"result-{source}", request.request_id, f"job-{source}",
                                  request.provider_id, "succeeded", output_references=(str(output),))
        return GenerationJob(f"job-{source}", request, status="succeeded", result=result)
    assert library.sync_job(job("REGENERATION_STUDIO")) == ()
    normal = library.sync_job(job("premium"))
    assert len(normal) == 1
    assert library.get(normal[0].image_id).image_id == normal[0].image_id


def test_start_reuses_active_background_operation_and_rejects_ineligible(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    workspace=MemoryWorkspace(); operation=SimpleNamespace(operation_id=uuid4())
    class Operations:
        def __init__(self): self.calls=0
        def create(self,**kwargs): self.calls+=1; return operation, self.calls==1
    operations=Operations(); service=RegenerationService(eligibility=eligibility,repository=workspace,recipes=recipes)
    first=service.start(source_generated_image_id=source.image_id,count=2,creator_profile_id=7,account_id=9,operations=operations)
    second=service.start(source_generated_image_id=source.image_id,count=2,creator_profile_id=7,account_id=9,operations=operations)
    assert first[1] is True and second[1] is False and len(workspace.results(operation.operation_id))==2
    eligibility.inspect=lambda _, **kwargs: RegenerationEligibility(False,"NO","No")
    with pytest.raises(RegenerationIneligible): service.start(source_generated_image_id=source.image_id,count=1,creator_profile_id=7,account_id=9,operations=operations)


def test_promotion_is_idempotent_library_registration_with_existing_recipe(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    new_recipe = recipe(source_workflow="REGENERATION_STUDIO", workflow_origin="regeneration",
                        source_generated_image_id=source.image_id, source_recipe_id=source_recipe.recipe_id,
                        regeneration_operation_id=uuid4())
    recipes.items[str(new_recipe.recipe_id)] = new_recipe
    recipes.executions[str(new_recipe.recipe_id)] = GenerationRecipeExecution(new_recipe.recipe_id, "SUCCEEDED", "one-existing-request")
    media = tmp_path / "variation.png"; media.write_bytes(b"existing pixels")
    operation_id = new_recipe.regeneration_operation_id
    result_id = uuid4()
    workspace = MemoryWorkspace()
    workspace.runs[operation_id] = RegenerationRun(operation_id, 7, source.image_id, source_recipe.recipe_id, 1, "SUCCEEDED")
    workspace.rows[operation_id] = [RegenerationResult(
        result_id, operation_id, 1, "SUCCEEDED", "job-1", "engine-result-1",
        "promoted-image", new_recipe.recipe_id, str(media), "PENDING_REVIEW",
    )]
    job = GenerationJob("job-1", GenerationRequest(
        "request-1", 7, "plan", new_recipe.final_prompt, 93, "identity.png",
        "seedream_5_0_pro", "image_to_image", "image",
        metadata={"source": "REGENERATION_STUDIO", "source_generated_image_id": source.image_id},
    ), status="succeeded", result=GenerationResult(
        "engine-result-1", "request-1", "job-1", "seedream_5_0_pro", "succeeded",
        generation_metadata={"output_generation_recipe_ids": (str(new_recipe.recipe_id),)},
        output_references=(str(media),),
    ))
    class Operations:
        def get(self, *args, **kwargs): return SimpleNamespace(operation_id=operation_id)
    class Library:
        def __init__(self): self.calls=[]
        def promote_regeneration_result(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(image_id=kwargs["generated_image_id"], generation_recipe_id=kwargs["generation_recipe_id"]), len(self.calls) == 1
    library = Library()
    service = RegenerationService(
        eligibility=eligibility, repository=workspace, recipes=recipes,
        generation_engine=SimpleNamespace(get_job=lambda _: job),
    )
    workspace.archive_result(operation_id, result_id)
    first = service.promote(operation_id, [str(result_id)], creator_profile_id=7, account_id=9, operations=Operations(), generation_library=library)
    second = service.promote(operation_id, [str(result_id)], creator_profile_id=7, account_id=9, operations=Operations(), generation_library=library)
    assert first[0].generation_recipe_id == str(new_recipe.recipe_id)
    assert second[0].image_id == "promoted-image"
    assert workspace.results(operation_id)[0].disposition == "PROMOTED"
    assert media.read_bytes() == b"existing pixels"
    assert recipes.get(new_recipe.recipe_id) is new_recipe


def test_promoted_library_record_is_copied_once_and_becomes_regeneration_eligible(tmp_path):
    eligibility, source, source_recipe, recipes, reference = eligibility_fixture(tmp_path)
    operation_id=uuid4(); promoted_image_id="promoted-image"
    new_recipe=recipe(source_workflow="REGENERATION_STUDIO",workflow_origin="regeneration",
                      source_generated_image_id=source.image_id,source_recipe_id=source_recipe.recipe_id,
                      regeneration_operation_id=operation_id)
    recipes.items[str(new_recipe.recipe_id)]=new_recipe
    recipes.executions[str(new_recipe.recipe_id)]=GenerationRecipeExecution(new_recipe.recipe_id,"SUCCEEDED","provider-once")
    recipes.output_rows[str(new_recipe.recipe_id)]=[GenerationRecipeOutput(uuid4(),new_recipe.recipe_id,"result",promoted_image_id,0)]
    workspace=tmp_path/"workspace.png"; workspace.write_bytes(b"unchanged workspace pixels")
    job=GenerationJob("job",GenerationRequest("request",7,"plan",new_recipe.final_prompt,93,str(reference),
        "seedream_5_0_pro","image_to_image","image",metadata={"source":"REGENERATION_STUDIO","workflow_type":"REGENERATION_STUDIO","workflow_origin":"regeneration"}),
        status="succeeded",result=GenerationResult("result","request","job","seedream_5_0_pro","succeeded",
        generation_metadata={"output_generation_recipe_ids":(str(new_recipe.recipe_id),)},output_references=(str(workspace),)))
    class Archive:
        def copy_generation(self, record):
            target=tmp_path/"active"/f"{record.image_id}.png"; target.parent.mkdir(); target.write_bytes(Path(record.output_reference).read_bytes())
            return replace(record,output_reference=str(target))
    library=GenerationLibraryService(storage_dir=tmp_path/"library",archive_service=Archive())
    first,created=library.promote_regeneration_result(job=job,media_path=str(workspace),generated_image_id=promoted_image_id,generation_recipe_id=str(new_recipe.recipe_id))
    second,created_again=library.promote_regeneration_result(job=job,media_path=str(workspace),generated_image_id=promoted_image_id,generation_recipe_id=str(new_recipe.recipe_id))
    assert created is True and created_again is False
    assert first.image_id==second.image_id and first.output_reference==second.output_reference
    assert workspace.read_bytes()==b"unchanged workspace pixels"
    assert len(library.list_records())==1 and first.generation_recipe_id==str(new_recipe.recipe_id)
    promoted_eligibility=RegenerationEligibilityService(generation_library=library,recipes=recipes,
        references=ReferenceService(reference),provider_registry=ProviderRegistry()).inspect(promoted_image_id,creator_profile_id=7)
    assert promoted_eligibility.can_regenerate


def test_archive_and_restore_preserve_media_recipe_and_lineage(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    operation_id = uuid4(); result_id = uuid4(); media = tmp_path / "variation.png"; media.write_bytes(b"pixels")
    generated_recipe = recipe(source_workflow="REGENERATION_STUDIO", workflow_origin="regeneration",
                              source_generated_image_id=source.image_id, source_recipe_id=source_recipe.recipe_id,
                              regeneration_operation_id=operation_id)
    recipes.items[str(generated_recipe.recipe_id)] = generated_recipe
    workspace = MemoryWorkspace()
    workspace.runs[operation_id] = RegenerationRun(operation_id, 7, source.image_id, source_recipe.recipe_id, 1, "SUCCEEDED")
    workspace.rows[operation_id] = [RegenerationResult(
        result_id, operation_id, 1, "SUCCEEDED", "job", "result", "generated-image",
        generated_recipe.recipe_id, str(media), "PENDING_REVIEW",
    )]
    operations = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(operation_id=operation_id))
    service = RegenerationService(eligibility=eligibility, repository=workspace, recipes=recipes)

    archived = service.archive(operation_id, [str(result_id)], creator_profile_id=7, account_id=9, operations=operations)
    archived_again = service.archive(operation_id, [str(result_id)], creator_profile_id=7, account_id=9, operations=operations)
    assert archived[0].disposition == archived_again[0].disposition == "ARCHIVED"
    assert media.read_bytes() == b"pixels"
    assert recipes.get(generated_recipe.recipe_id).source_recipe_id == source_recipe.recipe_id

    restored = service.restore(operation_id, str(result_id), creator_profile_id=7, account_id=9, operations=operations)
    assert restored.disposition == "PENDING_REVIEW"
    assert media.read_bytes() == b"pixels"


def test_archive_rejects_promoted_and_failed_results(tmp_path):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    operation_id = uuid4(); media = tmp_path / "variation.png"; media.write_bytes(b"pixels")
    workspace = MemoryWorkspace()
    workspace.runs[operation_id] = RegenerationRun(operation_id, 7, source.image_id, source_recipe.recipe_id, 2, "PARTIAL")
    workspace.rows[operation_id] = [
        RegenerationResult(uuid4(), operation_id, 1, "SUCCEEDED", "job", "result", "one", source_recipe.recipe_id, str(media), "PROMOTED"),
        RegenerationResult(uuid4(), operation_id, 2, "FAILED", disposition="PENDING_REVIEW"),
    ]
    operations = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(operation_id=operation_id))
    service = RegenerationService(eligibility=eligibility, repository=workspace, recipes=recipes)
    with pytest.raises(ValueError, match="Promoted"):
        service.archive(operation_id, [str(workspace.rows[operation_id][0].regeneration_result_id)], creator_profile_id=7, account_id=9, operations=operations)
    with pytest.raises(ValueError, match="Only successful"):
        service.archive(operation_id, [str(workspace.rows[operation_id][1].regeneration_result_id)], creator_profile_id=7, account_id=9, operations=operations)


@pytest.mark.parametrize("mutation,message", [
    ("foreign", "does not belong"), ("failed", "Only successful"),
    ("missing_media", "unavailable"), ("missing_recipe", "no Generation Recipe"),
])
def test_promotion_rejects_invalid_results(tmp_path, mutation, message):
    eligibility, source, source_recipe, recipes, _ = eligibility_fixture(tmp_path)
    operation_id=uuid4(); result_id=uuid4(); media=tmp_path/"result.png"; media.write_bytes(b"x")
    workspace=MemoryWorkspace(); workspace.runs[operation_id]=RegenerationRun(operation_id,7,source.image_id,source_recipe.recipe_id,1,"SUCCEEDED")
    item=RegenerationResult(result_id,operation_id,1,"SUCCEEDED","job","result","image",source_recipe.recipe_id,str(media),"PENDING_REVIEW")
    if mutation=="failed": item=replace(item,status="FAILED")
    if mutation=="missing_media": item=replace(item,media_path=str(tmp_path/"missing.png"))
    if mutation=="missing_recipe": item=replace(item,generation_recipe_id=None)
    workspace.rows[operation_id]=[item]
    class Operations:
        def get(self,*args,**kwargs): return object()
    selected = str(uuid4()) if mutation=="foreign" else str(result_id)
    with pytest.raises(ValueError,match=message):
        RegenerationService(eligibility=eligibility,repository=workspace,recipes=recipes).promote(
            operation_id,[selected],creator_profile_id=7,account_id=9,operations=Operations(),generation_library=SimpleNamespace())
