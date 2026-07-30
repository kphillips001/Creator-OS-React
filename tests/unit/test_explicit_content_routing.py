from types import SimpleNamespace

from app.models.creative_director import PromptPlan
from app.services.canonical_prompt_planner import (
    CanonicalPromptPlanner,
    CanonicalPromptPlanningRequest,
)
from app.services.content_studio_generation_service import (
    ContentStudioGenerationService,
)
from app.services.creative_director_service import CreativeDirectorService


class ReferenceLibrary:
    def get_active_canonical_reference(self, **_kwargs):
        return None


def test_explicit_dispatcher_uses_canonical_planner_and_never_social_builder(
    monkeypatch, tmp_path
):
    service = CreativeDirectorService(
        storage_dir=tmp_path,
        reference_library_service=ReferenceLibrary(),
    )
    calls = []

    def canonical(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            prompts=("canonical explicit provider prompt",),
            prompt_builder="canonical_explicit_prompt_planner",
            mode="explicit",
            metadata={
                "canonical_planner": "creator_os",
                "planning_mode": "explicit",
            },
        )

    monkeypatch.setattr(service, "plan_prompts", canonical)
    monkeypatch.setattr(
        service,
        "build_diversified_prompt_batch",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit reached the social builder")
        ),
    )

    plan = service.create_prompt_plan(
        creator_profile={"id": 7},
        creative_tags="topless beside the window",
        creative_mode="explicit",
        prompt_count=1,
        metadata={
            "explicit_input": {
                "original_source": "standing topless beside the window"
            }
        },
    )

    assert calls[0]["mode"] == "explicit"
    assert calls[0]["metadata"]["original_source"] == (
        "standing topless beside the window"
    )
    assert plan.prompt_metadata["prompt_builder"] == (
        "canonical_explicit_prompt_planner"
    )
    assert plan.prompt_metadata["canonical_planner"] == "creator_os"
    assert plan.prompt_metadata["planning_mode"] == "explicit"


def test_social_dispatcher_remains_on_social_builder(monkeypatch, tmp_path):
    service = CreativeDirectorService(
        storage_dir=tmp_path,
        reference_library_service=ReferenceLibrary(),
    )
    calls = []
    monkeypatch.setattr(
        service,
        "build_diversified_prompt_batch",
        lambda **kwargs: calls.append(kwargs) or ("social provider prompt",),
    )

    plan = service.create_prompt_plan(
        creator_profile={"id": 7},
        creative_tags="coffee shop portrait",
        creative_mode="social_safe",
        prompt_count=1,
    )

    assert len(calls) == 1
    assert calls[0]["creative_mode"] == "social_safe"
    assert plan.prompt_metadata["prompt_builder"] == (
        "wavespeed_social_prompt_builder"
    )


def test_original_source_participates_in_explicit_canonical_planning(monkeypatch):
    captured = {}

    def generate(**kwargs):
        captured.update(kwargs)
        return ["provider prompt"]

    monkeypatch.setattr(
        "app.services.canonical_prompt_planner.generate_explicit_prompts",
        generate,
    )
    result = CanonicalPromptPlanner().plan(
        CanonicalPromptPlanningRequest(
            mode="explicit",
            creative_tags="compact enhanced tags",
            prompt_count=1,
            metadata={
                "original_source": "fully nude at the bedroom window",
                "collection_id": "collection-1",
            },
        )
    )

    assert captured["enhanced_explicit_tags"] == "compact enhanced tags"
    assert captured["original_source"] == "fully nude at the bedroom window"
    assert result.metadata["explicit_input"]["collection_id"] == "collection-1"


class ProviderReadyDirector:
    def __init__(self):
        self.provider_calls = []
        self.planning_calls = []

    def create_provider_prompt_plan(self, **kwargs):
        self.provider_calls.append(kwargs)
        return PromptPlan(
            plan_id="provider-plan",
            session_id="provider-session",
            creator_profile_id=7,
            prompt_text=kwargs["prompts"][0],
            creative_mode="explicit",
            creative_tags=(kwargs["creative_tags"],),
            reference_asset_id=None,
            reference_asset_path=None,
            creative_rationale="provider ready",
            prompt_metadata={
                "prompt_variations": kwargs["prompts"],
                **kwargs["metadata"],
            },
        )

    def create_prompt_plan(self, **kwargs):
        self.planning_calls.append(kwargs)
        raise AssertionError("provider-ready explicit generation replanned")


def test_provider_ready_explicit_prompt_is_not_replanned():
    director = ProviderReadyDirector()
    engine = SimpleNamespace(
        queue_prompt_plan=lambda **_kwargs: SimpleNamespace(job_id="job-1")
    )
    service = ContentStudioGenerationService(
        creative_director=director,
        generation_engine=engine,
        generation_library=SimpleNamespace(),
        reference_service=SimpleNamespace(),
    )
    explicit_input = {
        "original_source": "topless beside the window",
        "collection_id": "collection-1",
    }

    plan, _job = service.queue(
        creator_profile={"id": 7},
        creative_tags="enhanced tags",
        creative_mode="explicit",
        prompt_count=1,
        provider_id="seedream_5_0_pro",
        prompt_batch=("exact preview provider prompt",),
        origin="explicit_inspiration",
        planner_lineage={"selectedPlannerItem": "topless beside the window"},
        explicit_input=explicit_input,
    )

    assert director.planning_calls == []
    assert director.provider_calls[0]["prompts"] == (
        "exact preview provider prompt",
    )
    assert plan.prompt_metadata["explicit_input"] == explicit_input
