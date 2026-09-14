from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.customer_visual_evidence_policy import CustomerVisualEvidencePolicy, VisualEvidenceClass


def test_visual_observations_are_ephemeral_and_not_memory_authority():
    observations = [{"attachment_id": "a", "person_visible": True, "person_count": 1,
                     "dog_visible": False, "animal_visible": False, "animals": [], "objects": [],
                     "activity": None, "broad_scene": "portrait", "smiling": True,
                     "style_or_clothing_summary": "casual", "screenshot_or_meme": False,
                     "visible_text_summary": None, "confidence": .9}]
    sanitized, audit = CustomerVisualEvidencePolicy.sanitize_observations(observations)
    assert sanitized == observations
    assert audit["evidence_class"] == "EPHEMERAL_VISUAL_CONTEXT"
    assert CustomerVisualEvidencePolicy.classify(source="VISION") is VisualEvidenceClass.EPHEMERAL_VISUAL_CONTEXT
    assert ConversationalMemoryService.extract("") == {}


def test_customer_text_remains_independent_memory_authority():
    assert ConversationalMemoryService.extract_records("This is my dog Charlie")
    assert ConversationalMemoryService.extract_records("I moved to Denver")
    assert ConversationalMemoryService.extract_records("") == []


def test_unknown_sensitive_fields_are_discarded_and_never_persisted():
    sanitized, audit = CustomerVisualEvidencePolicy.sanitize_observations([
        {"attachment_id": "a", "person_visible": True, "race": "invented", "identity_vector": [1, 2]}])
    assert sanitized == [{"attachment_id": "a", "person_visible": True}]
    assert {"race", "identity_vector"} <= set(audit["unknown_or_prohibited_fields_discarded"])
    persisted = CustomerVisualEvidencePolicy.minimum_persisted_result({
        "operation_id": "op", "attachment_paths": ["secret.jpg"], "observations": sanitized,
        "customer_presented_self_image": True})
    assert persisted["visual_observations_persisted"] is False
    assert not ({"attachment_paths", "observations", "customer_presented_self_image"} & persisted.keys())
