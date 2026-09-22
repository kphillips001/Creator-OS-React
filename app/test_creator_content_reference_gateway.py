from types import SimpleNamespace

import pytest

from app.services.conversation_gateway import ConversationGateway
from app.test_current_turn_semantic_ordering import (
    ERIC_SEMANTICS,
    OneShotEngine,
    RecordingBrain,
    gateway_request,
)


class Resolver:
    def __init__(self, events): self.events = events
    def resolve(self, **_kwargs):
        self.events.append("resolver")
        context = {"publicationId": "mirror-one", "telegramMessageId": 501,
            "caption": "Mirror mood", "visualSummary": "mirror selfie",
            "clothing": "black strapless outfit", "confidence": .96}
        return SimpleNamespace(disposition="RESOLVED", context=context,
            diagnostics=lambda: {"referenceIntentDetected": True,
                "disposition": "RESOLVED", "resolutionMethod": "SEMANTIC_DATE_RANKING",
                "selectedPublicationId": "mirror-one", "selectedTelegramMessageId": 501,
                "confidence": .96, "candidatePublicationIds": ("mirror-one",),
                "supportingEvidence": ("SEMANTIC_TERM:mirror",),
                "contentContextVersion": "creator_content_reference_v1"})


class GroundedEngine(OneShotEngine):
    def __init__(self, events): super().__init__(); self.events = events
    def classify_current_turn(self, *, user_id, message, creator_content_context):
        self.events.append("classifier")
        self.classifier_context = dict(creator_content_context)
        self.classifier_calls += 1
        return dict(ERIC_SEMANTICS)


@pytest.mark.parametrize("historical", [False, True])
def test_reference_resolution_precedes_semantics_and_reaches_sales_brain_and_generation(historical):
    events = []
    engine = GroundedEngine(events)
    brain = RecordingBrain()
    result = ConversationGateway(engine, allowed_fanvue_hostnames=["fanvue.com"],
        customer_sales_brain_service=brain,
        creator_content_reference_resolver=Resolver(events)).execute(
            gateway_request(historical=historical))
    assert result.blocked is False
    assert events == ["resolver", "classifier"]
    assert engine.classifier_context["publicationId"] == "mirror-one"
    assert brain.contexts[0]["resolved_creator_content_context"]["publicationId"] == "mirror-one"
    assert engine.runtime["resolved_creator_content_context"]["publicationId"] == "mirror-one"
    diagnostics = result.diagnostic_metadata["creatorContentReference"]
    assert diagnostics["suppliedToSemanticClassifier"] is True
    assert diagnostics["suppliedToSalesBrain"] is True
    assert diagnostics["suppliedToGeneration"] is True
