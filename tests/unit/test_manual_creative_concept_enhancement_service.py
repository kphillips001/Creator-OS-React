from app.services.manual_creative_concept_enhancement_service import (
    ManualCreativeConceptEnhancementService,
)


class ContextBuilder:
    def __init__(self):
        self.calls = []

    def build_question(self, *, fanvue_account_id, question):
        self.calls.append((fanvue_account_id, question))
        return (
            "PRIVATE CREATOR CONTEXT: personality, lifestyle, social direction, "
            "world model, aggregated creative intelligence, July/summer\n"
            + question
        )


def test_manual_enhancement_uses_creator_context_and_preserves_operator_authority():
    context = ContextBuilder()
    captured = []
    service = ManualCreativeConceptEnhancementService(
        context_builder=context,
        text_generator=lambda prompt: captured.append(prompt) or (
            "Ava moves naturally along a wooded hiking trail in the operator-requested "
            "tight daisy duke shorts and crop top, interacting with the uneven path in "
            "warm directional light with candid editorial composition."
        ),
    )

    result = service.enhance(
        fanvue_account_id=2,
        creative_concept="tight booty daisy duke shorts, crop top, hiking",
    )

    assert context.calls[0][0] == "2"
    question = context.calls[0][1]
    assert "operator's Creative Concept is authoritative" in question
    assert "tight booty daisy duke shorts, crop top, hiking" in question
    assert "EDITORIAL CINEMATOGRAPHY — OBSERVED MOMENTS" in question
    assert "natural movement or environmental interaction" in question
    assert "camera distance, crop, perspective, composition, and lighting" in question
    assert "Do not invent pets, partners" in question
    assert "PRIVATE CREATOR CONTEXT" in captured[0]
    assert "daisy duke shorts and crop top" in result
    assert "hiking trail" in result


def test_manual_enhancement_is_account_scoped():
    context = ContextBuilder()
    service = ManualCreativeConceptEnhancementService(
        context_builder=context,
        text_generator=lambda _: "enhanced",
    )

    service.enhance(fanvue_account_id=11, creative_concept="Ava concept")
    service.enhance(fanvue_account_id=22, creative_concept="Amanda concept")

    assert [call[0] for call in context.calls] == ["11", "22"]


def test_manual_enhancement_falls_back_without_replacing_the_concept():
    service = ManualCreativeConceptEnhancementService(
        context_builder=ContextBuilder(),
        text_generator=lambda _: "",
    )

    assert service.enhance(
        fanvue_account_id=2,
        creative_concept="red crop top, lakeside walk",
    ) == "red crop top, lakeside walk"
