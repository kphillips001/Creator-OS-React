from dataclasses import replace
from datetime import timedelta

from app.services.conversation_gateway import ConversationGateway
from app.services.creator_content_reference_resolver import CreatorContentReferenceResolver
from app.test_creator_content_reference_gateway import GroundedEngine
from app.test_creator_content_reference_resolver import NOW, Repository, publication
from app.test_current_turn_semantic_ordering import RecordingBrain, gateway_request


class EntryRepository:
    def __init__(self, entries): self.entries=tuple(entries); self.calls=[]
    def list_entry_history(self, **kwargs):
        self.calls.append(kwargs)
        return self.entries[:kwargs["limit"]]


def entry(publication_id, *, event="entry-1", days=0):
    return {"entryEventId":event,"attributionId":f"attribution-{event}",
        "publicationId":publication_id,"observedAt":NOW-timedelta(days=days),
        "provenanceMethod":"TELEGRAM_DIRECT_CHAT_DRAFT"}


def resolver(values, entries=()):
    return CreatorContentReferenceResolver(repository=Repository(values),
        entry_repository=EntryRepository(entries))


def resolve(service, message, **kwargs):
    return service.resolve(creator_profile_id=7, inbound=message,
        current_timestamp=NOW, telegram_user_id=101, telegram_chat_id=101, **kwargs)


def test_vague_reaction_uses_latest_authoritative_entry_without_explicit_intent():
    result=resolve(resolver([publication("mirror",summary="mirror selfie")],[entry("mirror")]),"damn 😍")
    assert result.disposition == "RESOLVED"
    assert result.method == "CTA_ENTRY_PROVENANCE"
    assert result.context["publicationId"] == "mirror"
    diagnostics=result.diagnostics()
    assert diagnostics["entryPublicationId"] == "mirror"
    assert diagnostics["currentReferencedPublicationId"] == "mirror"
    assert diagnostics["ctaProvenanceParticipated"] is True


def test_same_publication_explicit_reference_is_corrobated_but_semantics_remain_authority():
    result=resolve(resolver([publication("mirror",summary="mirror selfie")],[entry("mirror")]),
        "Love that mirror selfie")
    assert result.disposition == "RESOLVED" and result.context["publicationId"] == "mirror"
    assert result.method == "SEMANTIC_DATE_RANKING"
    assert "CTA_ENTRY_CORROBORATES_EXPLICIT_REFERENCE" in result.evidence


def test_explicit_old_and_months_old_reference_override_new_entry_without_overwriting_it():
    values=[publication("new",summary="mirror selfie",age_days=0),
            publication("kayak",summary="yellow kayak picture by waterfall",age_days=180,message_id=2)]
    result=resolve(resolver(values,[entry("new")]),
        "I still think about that yellow kayak picture you posted months ago")
    diagnostics=result.diagnostics()
    assert result.disposition == "RESOLVED" and result.context["publicationId"] == "kayak"
    assert diagnostics["entryPublicationId"] == "new"
    assert diagnostics["explicitReferenceOverrodeCTA"] is True


def test_contradictory_explicit_reference_stays_ambiguous_instead_of_falling_back_to_entry():
    values=[publication("entry",summary="mirror selfie"),
            publication("hike-1",summary="hiking picture mountain trail",age_days=20,message_id=2),
            publication("hike-2",summary="hiking picture forest trail",age_days=22,message_id=3)]
    result=resolve(resolver(values,[entry("entry")]),"that hiking picture")
    assert result.disposition == "AMBIGUOUS" and result.context == {}
    assert result.diagnostics()["entryPublicationId"] == "entry"


def test_multiple_entries_keep_history_and_latest_only_informs_vague_message():
    history=(entry("friday",event="friday"),entry("monday",event="monday",days=4))
    service=resolver([publication("monday",summary="red dress"),
                      publication("friday",summary="mirror selfie",message_id=2)],history)
    vague=resolve(service,"wow 🔥")
    explicit=resolve(service,"that red dress picture")
    assert vague.context["publicationId"] == "friday"
    assert explicit.context["publicationId"] == "monday"
    assert explicit.diagnostics()["entryPublicationId"] == "friday"
    assert explicit.diagnostics()["explicitReferenceOverrodeCTA"] is True


def test_greeting_after_sexy_entry_retains_provenance_without_current_reference():
    item=publication("sexy",summary="sexy mirror selfie",explicit=True)
    result=resolve(resolver([item],[entry("sexy")]),"Hi Ava")
    diagnostics=result.diagnostics()
    assert result.disposition == "NONE" and result.context == {}
    assert diagnostics["entryAttributionAvailable"] is True
    assert diagnostics["currentReferencedPublicationId"] is None


def test_no_entry_and_publication_without_chat_cta_retain_part_1b_resolution():
    item=publication("hike",summary="hiking picture mountain trail",age_days=14)
    result=resolve(resolver([item]),"that hiking picture you posted two weeks ago")
    assert result.disposition == "RESOLVED" and result.context["publicationId"] == "hike"
    assert result.diagnostics()["entryAttributionAvailable"] is False


def test_reply_provenance_overrides_entry_authoritatively():
    values=[publication("entry",summary="mirror selfie",message_id=10),
            publication("reply",summary="yellow kayak",message_id=20)]
    result=resolve(resolver(values,[entry("entry")]),"wow",
        telegram_provenance={"reply_to_telegram_message_id":20})
    diagnostics=result.diagnostics()
    assert result.context["publicationId"] == "reply"
    assert diagnostics["entryPublicationId"] == "entry"
    assert diagnostics["replyProvenanceOverrodeCTA"] is True


def test_gateway_propagates_only_resolved_current_publication_and_durable_diagnostics():
    events=[]; engine=GroundedEngine(events); brain=RecordingBrain()
    service=resolver([publication("mirror",summary="mirror selfie",clothing="black strapless outfit")],
                     [entry("mirror")])
    request=replace(gateway_request(),message_text="damn 😍")
    result=ConversationGateway(engine,allowed_fanvue_hostnames=["fanvue.com"],
        customer_sales_brain_service=brain,creator_content_reference_resolver=service).execute(request)
    assert engine.classifier_context["publicationId"] == "mirror"
    assert brain.contexts[0]["resolved_creator_content_context"]["publicationId"] == "mirror"
    assert engine.runtime["resolved_creator_content_context"]["publicationId"] == "mirror"
    diagnostics=result.diagnostic_metadata["creatorContentReference"]
    assert diagnostics["entryPublicationId"] == "mirror"
    assert diagnostics["currentReferencedPublicationId"] == "mirror"
    assert diagnostics["suppliedToSemanticClassification"] is True
    assert diagnostics["suppliedToSalesBrain"] is True
    assert diagnostics["suppliedToGeneration"] is True