from app.services.canonical_ava_service import CanonicalAvaService


def test_canonical_ava_owns_identity_without_creative_direction():
    context = CanonicalAvaService().prompt_context()

    for identity_rule in (
        "exact same woman", "facial structure", "long dark loose hair",
        "natural sun-kissed skin tone", "full natural D-cup bust",
        "feminine hourglass body", "active canonical reference image",
    ):
        assert identity_rule in context

    assert "The creative direction controls scene, activity, wardrobe, pose, location, lighting, expression" in context


def test_manual_creative_direction_consumes_canonical_ava():
    captured = []
    service = __import__(
        "app.services.manual_creative_concept_enhancement_service",
        fromlist=["ManualCreativeConceptEnhancementService"],
    ).ManualCreativeConceptEnhancementService(
        context_builder=type("Context", (), {"build_question": lambda self, **values: values["question"]})(),
        text_generator=lambda prompt: captured.append(prompt) or "enhanced direction",
    )

    assert service.enhance(fanvue_account_id=2, creative_concept="rooftop concept") == "enhanced direction"
    assert "CANONICAL AVA — IDENTITY AUTHORITY" in captured[0]
    assert "full natural D-cup bust" in captured[0]


def test_non_creative_direction_caller_can_retain_phase_zero_behavior():
    captured = []
    service = __import__(
        "app.services.manual_creative_concept_enhancement_service",
        fromlist=["ManualCreativeConceptEnhancementService"],
    ).ManualCreativeConceptEnhancementService(
        context_builder=type("Context", (), {"build_question": lambda self, **values: values["question"]})(),
        text_generator=lambda prompt: captured.append(prompt) or "enhanced direction",
    )

    service.enhance(
        fanvue_account_id=2,
        creative_concept="recreate concept",
        include_canonical_ava=False,
    )
    assert "CANONICAL AVA — IDENTITY AUTHORITY" not in captured[0]
