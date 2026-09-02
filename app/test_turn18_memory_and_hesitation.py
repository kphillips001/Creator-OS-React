"""Turn 18 semantic-memory and commercial-hesitation regressions."""
from __future__ import annotations

import pytest

from app.models.commercial_objection import CommercialObjectionType
from app.services.commercial_objection_service import CommercialObjectionService
from app.services.conversational_memory_service import ConversationalMemoryService


NONCOMMERCIAL = (
    "I might get outside this weekend if the weather’s decent.",
    "I might go hiking Saturday.",
    "Maybe I'll go to the beach tomorrow.",
    "I'm not sure what I'm doing this weekend.",
    "I'll probably watch a movie later.",
    "Maybe I'll grab dinner soon.",
)

COMMERCIAL = (
    "Maybe I'll buy it later.",
    "I'm not sure I want that one yet.",
    "Let me think about the offer.",
    "Maybe later, I'm not ready to buy right now.",
    "I might get it later.",
)


@pytest.mark.parametrize("message", NONCOMMERCIAL)
def test_generic_uncertainty_is_not_a_commercial_objection(message):
    result = CommercialObjectionService().evaluate(
        message=message,
        context={"sales_progression": {
            "phase": "PRESENT_OFFER", "offeringId": "prior-offer",
        }},
    )
    assert result.objection_type is CommercialObjectionType.NONE
    assert result.evidence == ()
    assert result.pressure_decrease is False


@pytest.mark.parametrize("message", COMMERCIAL)
def test_commercially_linked_uncertainty_remains_temporary_hesitation(message):
    result = CommercialObjectionService().evaluate(
        message=message,
        context={"sales_progression": {
            "phase": "PRESENT_OFFER", "offeringId": "current-offer",
        }},
    )
    assert result.objection_type is CommercialObjectionType.TEMPORARY_HESITATION
    assert result.evidence == ("TEMPORARY_DELAY_LANGUAGE",)
    assert result.current_product_scoped is True
    assert result.pressure_decrease is True


def test_exact_turn18_combines_location_relevance_with_no_commercial_objection():
    message = "I might get outside this weekend if the weather’s decent."
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records("I'm in Chicago.")
    )
    memory = ConversationalMemoryService.retrieve(state, message)
    objection = CommercialObjectionService().evaluate(
        message=message,
        context={"sales_progression": {
            "phase": "PRESENT_OFFER", "offeringId": "prior-offer",
        }},
    )
    assert memory["timezone"] == "America/Chicago"
    assert memory["memoryDiagnostics"]["retrievedCount"] >= 1
    assert any(record["value"] == "Chicago"
               for record in memory["retrievedMemories"])
    assert objection.objection_type is CommercialObjectionType.NONE
    assert objection.pressure_decrease is False
