from app.services.photoshoot_naming_service import PhotoshootNamingService
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


def test_generates_title_and_description_from_aggregate_intelligence_only():
    captured = {}

    def runner(profile, count):
        captured.update(profile)
        captured["count"] = count
        return {"title": "Golden Hour Escape", "description": "A six-image outdoor collection with warm light and relaxed summer styling."}

    title, description = PhotoshootNamingService(runner=runner).generate(
        {"mood": ["relaxed"], "setting": ["meadow"], "overall_summary": "Warm outdoor sequence."}, 6
    )

    assert title == "Golden Hour Escape"
    assert description.startswith("A six-image")
    assert captured == {"mood": ["relaxed"], "setting": ["meadow"], "overall_summary": "Warm outdoor sequence.", "count": 6}


def test_rejects_internal_workflow_terms_and_identifiers():
    service = PhotoshootNamingService(runner=lambda *_: {"title": "Photoshoot Session 2026", "description": "A concise collection."})
    try:
        service.generate({}, 2)
        assert False, "Expected invalid title rejection."
    except ValueError as error:
        assert "2-5 words" in str(error)


def test_rejects_legacy_classification_language_in_title_or_description():
    for payload in (
        {"title": "Sunlit Outdoor Tease", "description": "A relaxed outdoor set."},
        {"title": "Sunlit Serenity", "description": "A suggestive outdoor set."},
    ):
        service = PhotoshootNamingService(runner=lambda *_args, value=payload: value)
        try:
            service.generate({}, 2)
            assert False, "Expected legacy terminology rejection."
        except ValueError as error:
            assert "legacy" in str(error)


def test_refinement_selection_is_idempotent_for_clean_ai_copy():
    service = PhotoshootNamingService(runner=lambda *_: {})
    assert service.needs_refinement("Sunlit Outdoor Tease", "A suggestive outdoor set.")
    assert service.needs_refinement(None, "A relaxed outdoor set.")
    assert not service.needs_refinement(
        "Sunlit Serenity",
        "A two-image outdoor lifestyle set featuring warm light and relaxed denim styling.",
    )


def test_refinement_replaces_only_ai_copy_and_preserves_user_overrides():
    class Naming:
        needs_refinement = staticmethod(PhotoshootNamingService.needs_refinement)

        @staticmethod
        def generate(_profile, _count):
            return "Sunlit Serenity", "A two-image outdoor lifestyle set in warm summer light."

    class Repository:
        def __init__(self):
            self.saved = None

        def set_ai_naming(self, deliverable_id, title, description):
            self.saved = (deliverable_id, title, description)

        def get_by_session(self, _session_id):
            return {
                **deliverable,
                "ai_title": self.saved[1],
                "ai_description": self.saved[2],
            }

    deliverable = {
        "deliverable_id": "set-1",
        "photoshoot_session_id": "session-1",
        "shot_count": 2,
        "ai_title": "Sunlit Outdoor Tease",
        "ai_description": "Two suggestive outdoor images.",
        "user_title": "My Summer Collection",
        "user_description": "My own description.",
    }
    repository = Repository()
    result = PhotoshootCommerceDeliverableService(repository=repository, naming=Naming())._ensure_naming(
        deliverable, {"mood": ["relaxed"]}, "READY"
    )

    assert repository.saved == (
        "set-1",
        "Sunlit Serenity",
        "A two-image outdoor lifestyle set in warm summer light.",
    )
    assert result["user_title"] == "My Summer Collection"
    assert result["user_description"] == "My own description."
