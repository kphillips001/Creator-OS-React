from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.creative_intelligence import CreativeImageAnalysis
from app.models.generation_library import GeneratedImageRecord
from app.services.creative_intelligence_learning_service import (
    CreativeImageAnalyzer,
    CreativeIntelligenceLearningService,
)
from app.services.generation_library_service import GenerationLibraryService
from app.repositories.creative_intelligence_repository import (
    CreativeIntelligenceRepository,
)


class MemoryRepository:
    def __init__(self):
        self.events = {}

    def record(self, signal):
        if signal.event_key in self.events:
            return {"already_recorded": True}
        self.events[signal.event_key] = signal
        return {"already_recorded": False}

    def get_profile(self, *, creator_profile_id, fanvue_account_id):
        return {
            "creator_profile_id": creator_profile_id,
            "fanvue_account_id": fanvue_account_id,
            "positive_event_count": 5,
            "negative_event_count": 1,
            "analyzed_image_count": 4,
            "learned_attributes": {
                "environment": {"dock": 3, "rooftop": 1},
                "composition": {"full body": 2},
                "unexpected": {"must": 99},
            },
        }


class FixedAnalyzer:
    provider_name = "test-vision"

    def __init__(self):
        self.references = []

    def analyze(self, image_reference):
        self.references.append(image_reference)
        return CreativeImageAnalysis(
            environment="beach",
            visual_style="confident",
            composition="full body",
            pose="walking",
            season="summer",
            lighting="golden hour",
            wardrobe_category="swimwear",
        )


def test_positive_signal_analyzes_actual_image_and_stores_only_categories():
    repository = MemoryRepository()
    analyzer = FixedAnalyzer()
    service = CreativeIntelligenceLearningService(
        repository=repository, analyzer=analyzer
    )

    service.record_positive(
        creator_profile_id=7,
        image_reference="kept-image.jpg",
        event_type="published",
        source_workflow="manual",
        source_image_id="image-1",
        operational_metadata={
            "platform": "x",
            "caption": "must not be stored",
            "prompt": "must not be stored",
            "hashtags": "#mustnotbestored",
        },
    )

    event = next(iter(repository.events.values()))
    assert analyzer.references == ["kept-image.jpg"]
    assert event.analysis.as_dict() == {
        "environment": "beach",
        "visual_style": "confident",
        "composition": "full body",
        "pose": "walking",
        "season": "summer",
        "lighting": "golden hour",
        "wardrobe_category": "swimwear",
    }
    assert event.operational_metadata == {"platform": "x"}


def test_repeated_boundary_event_is_idempotent():
    repository = MemoryRepository()
    service = CreativeIntelligenceLearningService(
        repository=repository, analyzer=FixedAnalyzer()
    )
    kwargs = dict(
        creator_profile_id=7,
        image_reference="kept-image.jpg",
        event_type="generation_library_retained",
        source_workflow="generation_library",
        source_image_id="image-1",
    )

    service.record_positive(**kwargs)
    service.record_positive(**kwargs)

    assert len(repository.events) == 1


def test_aggregated_profile_exposes_only_normalized_editorial_counts():
    service = CreativeIntelligenceLearningService(
        repository=MemoryRepository(), analyzer=FixedAnalyzer()
    )

    profile = service.get_aggregated_profile(
        creator_profile_id=7, fanvue_account_id="2"
    )

    assert profile["positive_event_count"] == 5
    assert dict(profile["learned_attributes"]["environment"]) == {
        "dock": 3,
        "rooftop": 1,
    }
    assert "unexpected" not in profile["learned_attributes"]


def test_primary_editorial_actions_have_stronger_aggregate_weights():
    assert CreativeIntelligenceRepository.POSITIVE_EVENT_WEIGHTS == {
        "published": 5,
        "photoshoot_added": 4,
        "generation_library_retained": 4,
        "edit_saved": 3,
    }


def test_negative_signal_is_lightweight_and_does_not_analyze():
    repository = MemoryRepository()
    analyzer = FixedAnalyzer()
    service = CreativeIntelligenceLearningService(
        repository=repository, analyzer=analyzer
    )

    service.record_negative(
        creator_profile_id=7,
        image_reference="discarded-image.jpg",
        event_type="inspire_discarded",
        source_workflow="autonomous_inspiration",
        source_image_id="image-2",
    )

    event = next(iter(repository.events.values()))
    assert analyzer.references == []
    assert event.signal == "negative"
    assert event.analysis_status == "not_required"
    assert event.analysis.as_dict() == {}


def test_image_analyzer_normalizes_coarse_categories_from_file(tmp_path: Path):
    image = tmp_path / "actual-image.jpg"
    image.write_bytes(b"actual image bytes")
    analyzer = CreativeImageAnalyzer(
        runner=lambda path: {
            "environment": "  Rooftop ",
            "visual_style": "Elegant",
            "composition": "Mid-shot",
            "pose": "Standing",
            "season": "Summer",
            "lighting": "Sunset",
            "wardrobe_category": "Dress",
        }
    )

    result = analyzer.analyze(str(image))

    assert result.environment == "rooftop"
    assert result.wardrobe_category == "dress"


def _generation_record(path: Path, *, source: str = "manual") -> GeneratedImageRecord:
    return GeneratedImageRecord(
        image_id="image-1",
        generation_job_id="job-1",
        generation_request_id="request-1",
        generation_result_id="result-1",
        output_reference=str(path),
        creator_profile_id=2,
        provider_id="test",
        prompt_plan_id="plan-1",
        prompt_text="never learned",
        creative_mode="test",
        reference_asset_id=None,
        generation_metadata={"source": source},
    )


def test_generation_library_retention_and_archive_use_shared_pipeline(tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"image")
    learner = Mock()
    archive = SimpleNamespace(
        archive_junk=lambda *args, **kwargs: None,
        content_paths=lambda: {"generation_active": tmp_path / "active"},
    )
    service = GenerationLibraryService(
        storage_dir=tmp_path / "library",
        archive_service=archive,
        creative_intelligence=learner,
    )
    record = _generation_record(image)
    service._write_records([record])

    service.move_to_asset_library(record.image_id)
    service.delete((record.image_id,))

    assert learner.record_positive_safely.call_args.kwargs["event_type"] == (
        "generation_library_retained"
    )
    assert learner.record_negative_safely.call_args.kwargs["event_type"] == "deleted"


def test_inspire_rejection_is_recorded_as_lightweight_negative(tmp_path: Path):
    image = tmp_path / "inspire.jpg"
    image.write_bytes(b"image")
    learner = Mock()
    archive = SimpleNamespace(
        archive_junk=lambda *args, **kwargs: None,
        content_paths=lambda: {"generation_active": tmp_path / "active"},
    )
    service = GenerationLibraryService(
        storage_dir=tmp_path / "library",
        archive_service=archive,
        creative_intelligence=learner,
    )
    record = _generation_record(image, source="autonomous_inspiration")
    service._write_records([record])

    service.delete((record.image_id,))

    assert learner.record_negative_safely.call_args.kwargs["event_type"] == (
        "inspire_discarded"
    )
