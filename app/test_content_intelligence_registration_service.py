import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.content_intelligence_profile import (
    ContentIntelligenceProfileStatus,
)
from app.services.content_intelligence_registration_service import (
    ContentIntelligenceRegistrationService,
)


class FakeProfileRepository:
    def __init__(self):
        self.records = {}
        self.upserts = []

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_profile(self, profile):
        self.records[int(profile.asset_id)] = profile
        self.upserts.append(profile)
        return profile

    def search_profiles(self, **kwargs):
        return tuple(self.records.values())


class FakeAssetRepository:
    def __init__(self, asset):
        self.asset = asset
        self.updates = []

    def get_by_id(self, asset_id):
        return self.asset if int(asset_id) == int(self.asset.id) else None

    def update_analysis_fields(self, asset_id, fields):
        self.updates.append((int(asset_id), fields))
        for key, value in fields.items():
            if key == "short_safe_summary":
                setattr(self.asset, "summary", value)
            elif key == "analysis_reasoning":
                setattr(self.asset, "reasoning", value)
            else:
                setattr(self.asset, key, value)


class FakeContentIntelligence:
    def build_from_asset(self, asset):
        return SimpleNamespace(
            asset_id=asset.id,
            asset_understanding=SimpleNamespace(asset_id=asset.id),
            summary=asset.summary,
            classification=asset.classification,
            confidence=asset.confidence,
            themes=tuple(asset.detected_themes),
            tags=tuple(asset.suggested_tags),
            mood=None,
            setting="studio",
            outfit=None,
            pose=None,
            activity="posing",
            objects=(),
            environment="studio",
            clothing=None,
            keywords=tuple(asset.suggested_tags),
            technical_quality={"has_runtime_media": asset.runtime_exists},
            media_metadata={"runtime_exists": asset.runtime_exists},
            ai_metadata={
                "gpt_vision_result": asset.gpt_vision_result,
                "classification_result": asset.classification_result,
            },
            technical_metadata={},
            provenance=asset.analysis_provenance,
            readiness={"has_runtime_media": asset.runtime_exists},
            ownership={},
            suggested_cover_image=None,
            recommendations={},
            to_context=lambda: {
                "asset_id": asset.id,
                "summary": asset.summary,
                "classification": asset.classification,
                "tags": tuple(asset.suggested_tags),
            },
        )


def make_asset(path, *, nudenet_enabled=False, runtime_exists=True):
    return SimpleNamespace(
        id=101,
        status="approved",
        file_path=str(path),
        file_name=Path(path).name,
        local_vault_path=str(path),
        media_type="image",
        upload_intent="teaser_image",
        media_metadata={
            "local_vault_path": str(path),
            "creator_approval": {
                "source_workflow": "generation_library",
                "source_item_id": "generated_image_1",
            },
        },
        summary="Soft teaser.",
        classification="TEASE",
        confidence=0.7,
        detected_themes=("studio",),
        suggested_tags=("tease",),
        risk_flags=(),
        reasoning="Existing vision.",
        analysis_provenance={"nudenet_enabled": nudenet_enabled},
        gpt_vision_result={
            "classification": "TEASE",
            "confidence": 0.7,
            "detected_themes": ["studio"],
            "suggested_tags": ["tease"],
            "short_safe_summary": "Soft teaser.",
            "reasoning": "Existing vision.",
            "risk_flags": [],
        },
        nudenet_result=[],
        classification_result={
            "final_classification": "TEASE",
            "raw_gpt_classification": "TEASE",
        },
        nudity_labels=(),
        nudity_level="none",
        sexual_intensity="low",
        is_explicit=False,
        runtime_exists=runtime_exists,
    )


class ContentIntelligenceRegistrationServiceTests(unittest.TestCase):
    def make_service(self, asset, *, profiles=None, nudenet_runner=None, vision_runner=None):
        profiles = profiles or FakeProfileRepository()
        return ContentIntelligenceRegistrationService(
            profile_repository=profiles,
            asset_repository=FakeAssetRepository(asset),
            content_intelligence_service=FakeContentIntelligence(),
            nudenet_runner=nudenet_runner or (lambda path: []),
            vision_runner=vision_runner
            or (
                lambda path, upload_intent: {
                    "classification": "TEASE",
                    "confidence": 0.8,
                    "detected_themes": ["studio"],
                    "suggested_tags": ["tease"],
                    "short_safe_summary": "Repaired vision.",
                    "reasoning": "Vision repaired.",
                    "risk_flags": [],
                }
            ),
            tier_rule_applier=lambda gpt, nudenet: {
                **dict(gpt),
                "raw_gpt_classification": gpt.get("classification"),
                "final_classification": (
                    "VIP"
                    if any(
                        item.get("class") == "FEMALE_BREAST_EXPOSED"
                        for item in nudenet
                        if isinstance(item, dict)
                    )
                    else gpt.get("classification", "TEASE")
                ),
                "rule_applied": (
                    "topless_or_exposed_breast_force_vip"
                    if any(
                        item.get("class") == "FEMALE_BREAST_EXPOSED"
                        for item in nudenet
                        if isinstance(item, dict)
                    )
                    else None
                ),
            },
        ), profiles

    def test_generation_asset_registration_persists_complete_profile_and_repairs_nudenet(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            asset = make_asset(file.name, nudenet_enabled=False)
            calls = []
            service, profiles = self.make_service(
                asset,
                nudenet_runner=lambda path: calls.append(path)
                or [{"class": "FEMALE_BREAST_EXPOSED"}],
            )

            profile = service.register_asset(
                101,
                source_workflow="generation_library",
            )

        self.assertEqual(profile.status, ContentIntelligenceProfileStatus.COMPLETE)
        self.assertTrue(profile.ready)
        self.assertEqual(calls, [Path(file.name)])
        self.assertEqual(asset.classification, "VIP")
        self.assertEqual(asset.nudity_labels, ("FEMALE_BREAST_EXPOSED",))
        self.assertEqual(asset.sexual_intensity, "medium")
        self.assertTrue(profiles.records[101].content_profile)

    def test_duplicate_complete_profile_reuses_without_reanalysis(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            asset = make_asset(file.name, nudenet_enabled=False)
            service, profiles = self.make_service(asset)
            first = service.register_asset(101, source_workflow="generation_library")
            calls = []
            service._nudenet_runner = lambda path: calls.append(path) or []

            second = service.register_asset(101, source_workflow="generation_library")

        self.assertIs(second, first)
        self.assertEqual(calls, [])
        self.assertEqual(len(profiles.upserts), 2)

    def test_complete_requires_runtime_media_and_required_analysis_components(self):
        missing_path = Path("missing-file-for-content-intelligence.png")
        asset = make_asset(missing_path, nudenet_enabled=False, runtime_exists=False)
        service, _ = self.make_service(asset)

        profile = service.register_asset(101, source_workflow="generation_library")

        self.assertEqual(profile.status, ContentIntelligenceProfileStatus.PARTIAL)
        self.assertIn("runtime_media", profile.missing_components)
        self.assertIn("nudenet", profile.missing_components)

    def test_failed_analysis_is_retryable(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            asset = make_asset(file.name, nudenet_enabled=False)

            def failing_vision(path, upload_intent):
                raise RuntimeError("vision unavailable")

            service, _ = self.make_service(asset, vision_runner=failing_vision)
            asset.gpt_vision_result = {}
            failed = service.register_asset(101, source_workflow="photoshoot")
            service._vision_runner = lambda path, upload_intent: {
                "classification": "TEASE",
                "confidence": 0.8,
                "detected_themes": ["studio"],
                "suggested_tags": ["tease"],
                "short_safe_summary": "Recovered.",
                "reasoning": "Recovered.",
                "risk_flags": [],
            }

            retried = service.retry_failed_components(101)

        self.assertEqual(failed.status, ContentIntelligenceProfileStatus.FAILED)
        self.assertEqual(retried.status, ContentIntelligenceProfileStatus.COMPLETE)
        self.assertGreaterEqual(retried.retry_count, 1)

    def test_unapproved_asset_does_not_receive_canonical_profile(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as file:
            asset = make_asset(file.name)
            asset.status = "pending_review"
            service, profiles = self.make_service(asset)

            profile = service.register_asset(101, source_workflow="generation_library")

        self.assertIsNone(profile)
        self.assertEqual(profiles.records, {})


if __name__ == "__main__":
    unittest.main()
