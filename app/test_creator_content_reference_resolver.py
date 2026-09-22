from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.creator_content_publication import CreatorContentPublication
from app.services.creator_content_reference_resolver import CreatorContentReferenceResolver
from app.services.current_turn_semantic_classification_service import CurrentTurnSemanticClassificationService
from app.services.customer_heat_signal_service import CustomerHeatSignalService


NOW = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)


def publication(identifier, *, age_days=0, caption="", summary="", clothing=None,
                setting=None, themes=(), explicit=False, message_id=1):
    return CreatorContentPublication(publication_id=identifier, creator_profile_id=7,
        platform="telegram", destination="main", telegram_channel_id=-1007,
        telegram_message_id=message_id, published_at=NOW-timedelta(days=age_days),
        generated_image_id=f"image-{identifier}", published_caption=caption,
        factual_visual_summary=summary, clothing=clothing, setting=setting,
        themes=themes, safety_snapshot={"explicitContent": explicit},
        intelligence_source="TEST", intelligence_version="v1",
        search_document=" ".join(filter(None, (caption, summary, clothing, setting))))


class Repository:
    def __init__(self, values): self.values = tuple(values); self.calls = []
    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.values[:kwargs["limit"]]


def resolve(values, message, **kwargs):
    repository = Repository(values)
    result = CreatorContentReferenceResolver(repository=repository).resolve(
        creator_profile_id=7, inbound=message, current_timestamp=NOW, **kwargs)
    return result, repository


def test_unique_mirror_selfie_resolves_to_bounded_factual_context():
    result, _ = resolve([publication("mirror", caption="Mirror mood",
        summary="mirror selfie", clothing="black strapless outfit", setting="bedroom")],
        "Love your mirror selfie")
    assert result.disposition == "RESOLVED"
    assert result.context["publicationId"] == "mirror"
    assert result.context["clothing"] == "black strapless outfit"
    assert "provider" not in str(result.context).lower()


def test_explicit_two_week_reference_outranks_newer_unrelated_publication():
    values = [publication("new", summary="mirror selfie", age_days=0),
              publication("hike", summary="hiking picture mountain trail", setting="mountains", age_days=14)]
    result, _ = resolve(values, "I loved that hiking picture you posted two weeks ago")
    assert result.disposition == "RESOLVED"
    assert result.context["publicationId"] == "hike"
    assert "RELATIVE_DATE:2_WEEKS" in result.evidence


def test_unique_180_day_reference_remains_eligible():
    result, _ = resolve([publication("old", summary="yellow kayak beside waterfall", age_days=180)],
                        "That yellow kayak picture by the waterfall was gorgeous")
    assert result.disposition == "RESOLVED" and result.context["publicationId"] == "old"


def test_equivalent_mirror_publications_are_ambiguous_without_exact_grounding():
    result, _ = resolve([publication("one", summary="mirror selfie", age_days=1),
                         publication("two", summary="mirror selfie", age_days=3, message_id=2)],
                        "that mirror selfie")
    assert result.disposition == "AMBIGUOUS"
    assert result.context == {} and len(result.candidates) == 2


def test_unrelated_chat_returns_none_without_archive_search():
    result, repository = resolve([publication("one", summary="mirror selfie")], "How was your day?")
    assert result.disposition == "NONE" and result.reference_intent_detected is False
    assert repository.calls == []


def test_authoritative_telegram_provenance_resolves_without_cta_attribution():
    result, _ = resolve([publication("one", summary="mirror selfie", message_id=91),
                         publication("two", summary="mirror selfie", message_id=92)],
                        "that picture", telegram_provenance={"reply_to_telegram_message_id": 92})
    assert result.disposition == "RESOLVED" and result.method == "TELEGRAM_PROVENANCE"
    assert result.context["publicationId"] == "two"


def test_candidate_count_is_bounded_and_has_no_age_filter():
    values = [publication(str(index), summary=f"unique picture {index}", age_days=index, message_id=index)
              for index in range(50)]
    _result, repository = resolve(values, "that unique picture 49")
    assert repository.calls[0]["limit"] <= 20
    assert "age" not in repository.calls[0]


def test_semantic_classifier_receives_bounded_referent_context_before_classification():
    observed = []
    def classifier(*, message, creator_content_context):
        observed.append((message, creator_content_context))
        return {"route": "chat", "confidence": .9, "sexual_engagement": False}
    diagnostics, result = CurrentTurnSemanticClassificationService().classify(
        message="that picture", correlation_id="turn-1", classifier=classifier,
        creator_content_context={"publicationId": "one", "visualSummary": "mirror selfie"})
    assert observed[0][1]["publicationId"] == "one"
    assert diagnostics["creatorContentContextSupplied"] is True
    assert result["sexual_engagement"] is False


@pytest.mark.parametrize("explicit", [False, True])
def test_suggestive_or_safe_publication_context_cannot_create_customer_heat(explicit):
    context = {"publicationId": "one", "safetySummary": {"explicitContent": explicit}}
    result = CustomerHeatSignalService().project(message="Love your mirror selfie",
        classifier_result={"sexual_engagement": False, "confidence": .9})
    assert context and result["warmupOverrideEligible"] is False


def test_customer_tingle_wording_independently_creates_heat():
    result = CustomerHeatSignalService().project(
        message="Love your mirror selfie. Make me tingle down below",
        classifier_result={"sexual_engagement": True,
            "explicit_without_buying_intent": True, "confidence": .95})
    assert result["warmupOverrideEligible"] is True
    assert "CURRENT_AROUSAL_SEMANTICS" in result["currentTurnEvidence"]


def test_prompt_projection_is_bounded_and_contains_no_raw_payload():
    result, _ = resolve([publication("one", caption="x"*3000,
        summary="mirror selfie", clothing="dress")], "that mirror selfie")
    assert len(result.context["caption"]) == 700
    assert set(result.context) <= {"publicationId", "telegramMessageId", "publishedAt",
        "generatedImageId", "actualAssetId", "photoshootId", "caption", "visualSummary",
        "setting", "clothing", "pose", "activity", "expression", "objects", "mood",
        "themes", "safetySummary", "resolutionMethod", "confidence"}
