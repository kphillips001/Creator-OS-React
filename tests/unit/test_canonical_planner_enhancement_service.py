from app.services.canonical_planner_enhancement_service import (
    CanonicalPlannerEnhancementService,
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


def test_planner_enhancement_uses_private_creator_context_and_preserves_scene():
    context = ContextBuilder()
    captured = []
    service = CanonicalPlannerEnhancementService(
        context_builder=context,
        text_generator=lambda prompt: captured.append(prompt) or (
            "Ava in a coral crop top and denim shorts, walking beside the marina "
            "at sunset, brushing her hair back while glancing toward the water, "
            "confident feminine styling, candid asymmetrical editorial moment"
        ),
    )

    result = service.enhance(
        fanvue_account_id=2,
        selected_item=(
            "Golden Hour Marina Walk — Ava wears a coral crop top and denim "
            "shorts while walking beside the marina at sunset, brushing her "
            "hair back as she glances toward the water."
        ),
    )

    assert context.calls[0][0] == "2"
    question = context.calls[0][1]
    assert "How would Ava" in question
    assert "naturally bring this selected concept to life?" in question
    assert "coral crop top and denim shorts" in question
    assert "walking beside the marina at sunset" in question
    assert "Editorial Cinematography" in question
    assert "static centered portrait or generic apartment" in question
    assert "Do not invent pets, partners" in question
    assert "PRIVATE CREATOR CONTEXT" in captured[0]
    assert "brushing her hair back" in result
    assert "glancing toward the water" in result


def test_planner_enhancement_is_account_scoped():
    context = ContextBuilder()
    service = CanonicalPlannerEnhancementService(
        context_builder=context,
        text_generator=lambda _: "enhanced",
    )
    service.enhance(fanvue_account_id=11, selected_item="Ava concept")
    service.enhance(fanvue_account_id=22, selected_item="Amanda concept")
    assert [call[0] for call in context.calls] == ["11", "22"]
