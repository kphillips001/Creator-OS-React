from datetime import datetime, timezone

from app.services.ava_temporal_context_service import AvaTemporalContextService
from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.telegram_response_pacing_service import TelegramResponsePacingService
from app.engine.decision_engine import DecisionEngine
from app.services.gpt_service import GPTService
from app.models.conversation_gateway import ConversationBrainContext, ConversationGatewayInput
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.models.telegram_inbound import TelegramInboundPayload
from unittest.mock import patch
import pytest


def test_shadow_pacing_runs_real_calculation_without_wait():
    service = TelegramResponsePacingService(variance=lambda: 1.0)
    short = service.calculate(inbound_text="lol", reply_text="maybe I do", shadow=True)
    longer = service.calculate(inbound_text="Tell me what you were thinking about",
                               reply_text="I was thinking about you for a minute. It caught me off guard.",
                               shadow=True)
    assert short.mode == "SHADOW" and short.applied_delay_ms == 0
    assert short.calculated_delay_ms > 0
    assert longer.calculated_delay_ms > short.calculated_delay_ms


def test_commerce_pacing_is_responsive_and_deterministic():
    service = TelegramResponsePacingService(variance=lambda: 1.0)
    result = service.calculate(inbound_text="How much is it?", reply_text="It's ready for you.",
                               commercial=True)
    assert result.mode == "APPLIED"
    assert result.calculated_delay_ms == result.applied_delay_ms
    assert "commerce" in result.reason


def test_ava_timezone_observes_est_and_edt():
    winter = AvaTemporalContextService(clock=lambda: datetime(2026, 1, 15, 17, tzinfo=timezone.utc)).build()
    summer = AvaTemporalContextService(clock=lambda: datetime(2026, 7, 15, 16, tzinfo=timezone.utc)).build()
    assert winter["avaLocalTime"].endswith("-05:00")
    assert summer["avaLocalTime"].endswith("-04:00")
    assert winter["avaTimezone"] == summer["avaTimezone"] == "America/New_York"


def test_unambiguous_location_and_stable_facts_are_extracted_conservatively():
    assert ConversationalMemoryService.extract("I'm from London") == {
        "location": "London", "timezone": "Europe/London"}
    ambiguous = ConversationalMemoryService.extract("I'm from Springfield")
    assert ambiguous["location"] == "Springfield"
    assert ambiguous["timezone"] is None
    assert ConversationalMemoryService.extract("My favorite color is blue")["favoriteColor"] == "blue"
    assert ConversationalMemoryService.extract("I have a dog named Milo")["pet"]["name"] == "Milo"


def test_social_style_disclosure_persists_and_is_retrieved_only_when_relevant():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    records = service.extract_records(
        "I'm usually pretty quiet at first. Takes me a minute to warm up to somebody."
    )
    service._merge_records(state, records)
    assert [(record["category"], record["key"]) for record in records] == [
        ("trait", "social_style")
    ]

    relevant = service.retrieve(
        state, "guess I'm getting more comfortable and opening up now"
    )
    assert relevant["memoryDiagnostics"]["retrievedKeys"] == ["social_style"]
    assert relevant["memoryDiagnostics"]["continuityGuidance"]["maximumCallbacks"] == 1

    unrelated = service.retrieve(state, "what are you having for dinner?")
    assert unrelated["memoryDiagnostics"]["retrievedCount"] == 0
    assert unrelated["memoryDiagnostics"]["continuityGuidance"]["maximumCallbacks"] == 0


def test_ephemeral_customer_activity_does_not_persist_as_memory():
    assert ConversationalMemoryService.extract_records("I'm just drinking water.") == []
    assert ConversationalMemoryService.extract_records("I'm sitting on the couch.") == []


def test_outdoors_interests_are_normalized_deduplicated_and_retrieved_relevantly():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    first = service.extract_records(
        "I'm kinda an outdoors person once I get off the couch 😂 hiking, camping, stuff like that."
    )
    service._merge_records(state, first)
    service._merge_records(
        state, service.extract_records("I went hiking this weekend."),
    )
    current = [record for record in state["records"] if record["status"] == "current"]
    assert {(record["category"], record["key"], record["value"]) for record in current} >= {
        ("interest", "outdoors", "outdoors"),
        ("hobby", "hiking", "hiking"),
        ("hobby", "camping", "camping"),
    }
    assert sum(record["key"] == "hiking" for record in current) == 1

    relevant = service.retrieve(state, "I finally got outside this weekend.")
    assert set(relevant["memoryDiagnostics"]["retrievedKeys"]) >= {
        "outdoors", "hiking", "camping",
    }
    unrelated = service.retrieve(state, "I had tacos for dinner.")
    assert unrelated["memoryDiagnostics"]["retrievedCount"] == 0


def test_interest_memory_coexists_with_social_style_memory():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    for message in (
        "I'm usually pretty quiet at first. Takes me a minute to warm up to somebody.",
        "I'm really into hiking and camping.",
    ):
        service._merge_records(state, service.extract_records(message))
    current_keys = {record["key"] for record in state["records"]
                    if record["status"] == "current"}
    assert {"social_style", "hiking", "camping"} <= current_keys


def test_explicit_memory_reference_ranks_social_style_above_hiking_without_duplicates():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    for message in (
        "I'm usually pretty quiet at first. Takes me a minute to warm up to somebody.",
        "I'm kinda an outdoors person once I get off the couch - hiking, camping, stuff like that.",
    ):
        service._merge_records(state, service.extract_records(message))
    before = [(item["category"], item["key"]) for item in state["records"]
              if item["status"] == "current"]

    result = service.retrieve(
        state,
        "See - told you I warm up eventually. I could talk about hiking forever.",
    )
    diagnostics = result["memoryDiagnostics"]
    candidates = diagnostics["memoryCandidates"]

    assert diagnostics["explicitMemoryReference"] is True
    assert {"social_style", "hiking", "outdoors"} <= {
        item["key"] for item in candidates
    }
    assert candidates[0]["key"] == "social_style"
    assert candidates[0]["relevanceScore"] > next(
        item["relevanceScore"] for item in candidates if item["key"] == "hiking"
    )
    assert diagnostics["continuityGuidance"]["priority"] == "HIGH"
    assert diagnostics["continuityGuidance"]["maximumCallbacks"] == 1
    assert diagnostics["continuityGuidance"]["strongestMemory"]["key"] == "social_style"
    assert "EXPLICIT_MEMORY_REFERENCE" in diagnostics["continuityGuidance"]["relevanceReasons"]
    assert service.extract_records(
        "See - told you I warm up eventually. I could talk about hiking forever."
    ) == []
    assert before == [(item["category"], item["key"]) for item in state["records"]
                      if item["status"] == "current"]


@pytest.mark.parametrize(("place", "expected"), (
    ("Chicago", "America/Chicago"),
    ("New York", "America/New_York"),
    ("Los Angeles", "America/Los_Angeles"),
))
def test_common_unambiguous_locations_resolve_deterministically(place, expected):
    result = ConversationalMemoryService.extract(f"I live in {place}.")
    assert result["location"] == place
    assert result["timezone"] == expected


def test_live_turn_16_here_in_chicago_extracts_bounded_location_and_timezone():
    message = (
        "It’s still afternoon here in Chicago — what are you up to this evening?"
    )
    records = ConversationalMemoryService.extract_records(message)
    location = next(record for record in records if record["key"] == "location")
    timezone_record = next(
        record for record in records if record["key"] == "timezone"
    )
    assert location.items() >= {
        "value": "Chicago",
        "source": "customer_volunteered_telegram",
        "confidence": .98,
    }.items()
    assert timezone_record.items() >= {
        "value": "America/Chicago",
        "source": "deterministic_location_inference",
        "confidence": .99,
    }.items()
    assert timezone_record["metadata"] == {
        "inference": "IANA_LOCALITY", "resolved": True,
    }


@pytest.mark.parametrize("message", (
    "I'm here in the chat",
    "I'm here in bed",
    "I'm here in my room",
    "I'm here in the app",
    "I'm here in this photo",
    "I'm here in line",
    "I'm here in the middle of something",
))
def test_here_in_non_geographic_context_does_not_create_location(message):
    records = ConversationalMemoryService.extract_records(message)
    assert not any(record["key"] in {"location", "timezone"} for record in records)


def test_live_turn_16_location_persists_and_reaches_same_turn_temporal_context():
    class Repository:
        def __init__(self): self.value = None
        def get(self, **_): return self.value
        def observe(self, **_):
            from types import SimpleNamespace
            self.value = SimpleNamespace(preference_state={})
            return self.value
        def merge_conversational_memory(self, *, values, **_):
            from types import SimpleNamespace
            self.value = SimpleNamespace(preference_state=dict(values))
            return self.value

    class Engine:
        def __init__(self): self.injection = None
        def process_message(self, user_id, message, chat_history=None,
                            runtime_injection=None):
            self.injection = runtime_injection
            return {"response": "Natural evening reply.", "send_offer": False,
                    "offer": {"offer_type": "none", "content": None}}

    repository = Repository()
    engine = Engine()
    memory_service = ConversationalMemoryService(repository=repository)
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=ConversationGateway(
            engine, allowed_fanvue_hostnames=["fanvue.com"],
            creator_profile_id=2,
        ),
        creator_profile_id=2, fanvue_account_id=2,
        conversational_memory_service=memory_service,
    )
    message = (
        "It’s still afternoon here in Chicago — what are you up to this evening?"
    )
    with patch(
        "app.services.private_chat_unlock_gateway_service.fingerprint_bootstrap_enabled",
        return_value=False,
    ):
        output = adapter.execute(TelegramInboundPayload(
            telegram_user_id=123, telegram_chat_id=123,
            message_text=message, message_id=16,
        ))

    persisted = repository.value.preference_state
    assert persisted["location"] == "Chicago"
    assert persisted["timezone"] == "America/Chicago"
    assert persisted["lastExtraction"]["locationTimezoneInference"] == {
        "location": "Chicago", "timezone": "America/Chicago", "resolved": True,
    }
    assert engine.injection["conversational_memory"]["timezone"] == (
        "America/Chicago"
    )
    assert engine.injection["time_context"]["avaTimezone"] == "America/New_York"
    assert engine.injection["time_context"]["customerTimezone"] == (
        "America/Chicago"
    )
    assert output.diagnostic_metadata["time_context"]["customerTimezone"] == (
        "America/Chicago"
    )

    reconstructed = ConversationalMemoryService(repository=repository)
    later = reconstructed.learn(
        creator_profile_id=2, fanvue_account_id=2,
        telegram_user_id=123, telegram_chat_id=123,
        message_text="Where did I tell you I live?",
    )
    assert later["timezone"] == "America/Chicago"
    assert later["location"] == "Chicago"


@pytest.mark.parametrize("message", (
    "I might get outside this weekend if the weather’s decent.",
    "Think it'll be nice enough to hike this weekend?",
    "Anything fun to do outside around here?",
    "The weather looks rough tomorrow.",
))
def test_location_memory_is_retrieved_for_geographically_dependent_context(message):
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records("I'm in Chicago.")
    )
    result = ConversationalMemoryService.retrieve(state, message)
    assert result["timezone"] == "America/Chicago"
    assert any(
        record["key"] == "location" and record["value"] == "Chicago"
        for record in result["retrievedMemories"]
    )
    assert result["memoryDiagnostics"]["retrievalAttempted"] is True
    assert result["memoryDiagnostics"]["retrievedCount"] >= 1


@pytest.mark.parametrize("message", (
    "That movie was hilarious.",
    "I've been listening to music all night.",
    "My dog is being ridiculous today.",
    "I'm tired.",
))
def test_location_memory_is_not_retrieved_for_unrelated_context(message):
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records("I'm in Chicago.")
    )
    result = ConversationalMemoryService.retrieve(state, message)
    assert not any(
        record["key"] in {"location", "timezone"}
        for record in result["retrievedMemories"]
    )


def test_pacing_diagnostics_distinguish_calculated_applied_and_bypassed():
    service = TelegramResponsePacingService(variance=lambda: 1.0)
    applied = service.calculate(inbound_text="hey", reply_text="hey you", shadow=False).diagnostics()
    shadow = service.calculate(inbound_text="hey", reply_text="hey you", shadow=True).diagnostics()
    assert applied["canonicalSource"] == "TelegramResponsePacingService"
    assert applied["applied"] is True and applied["bypassed"] is False
    assert applied["typingBehavior"] == "BOUNDED_PRE_SEND_DELAY"
    assert shadow["applied"] is False and shadow["bypassReason"] == "SHADOW_MODE"


def test_session_5_bypass_is_only_for_controlled_identity(monkeypatch):
    monkeypatch.setenv("SESSION_5_PACING_BYPASS_ENABLED", "true")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_USER_ID", "7857064998")
    service = TelegramResponsePacingService(variance=lambda: 1.0)
    controlled = service.calculate(
        inbound_text="long day", reply_text="yeah, I feel that",
        telegram_user_id=7857064998,
    ).diagnostics()
    other = service.calculate(
        inbound_text="long day", reply_text="yeah, I feel that",
        telegram_user_id=7857064999,
    ).diagnostics()
    assert controlled["calculatedDelayMs"] > 0
    assert controlled["appliedDelayMs"] == 0
    assert controlled["mode"] == "SESSION_5_TEST_BYPASS"
    assert controlled["bypassReason"] == "SESSION_5_ADVERSARIAL_CERTIFICATION"
    assert controlled["restoreMarker"] == "SESSION_5_PACING_BYPASS_ACTIVE"
    assert controlled["certificationExitRequired"] is True
    assert other["appliedDelayMs"] == other["calculatedDelayMs"] > 0
    assert other["bypassed"] is False


def test_session_5_bypass_disabled_restores_production_wait(monkeypatch):
    monkeypatch.setenv("SESSION_5_PACING_BYPASS_ENABLED", "false")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_USER_ID", "7857064998")
    decision = TelegramResponsePacingService(variance=lambda: 1.0).calculate(
        inbound_text="hey", reply_text="hey you", telegram_user_id=7857064998,
    )
    assert decision.mode == "APPLIED"
    assert decision.applied_delay_ms == decision.calculated_delay_ms > 0
    assert decision.bypass_reason is None


def test_supervised_runtime_applies_pacing_before_durable_send_claim():
    import inspect
    from app.integrations.telegram.telethon_runtime import TelethonRuntime
    source = inspect.getsource(TelethonRuntime._handle_authorized_payload)
    assert "shadow=False" in source
    assert source.index("response_deferred") < source.index(
        "self._response_pacing.calculate"
    )
    assert source.index("self._response_pacing.wait") < source.index(
        "self._sales_deliveries.claim"
    )
    assert source.index("self._response_pacing.wait") < source.index(
        "self._ordinary_replies.claim_send"
    )


def test_conversational_memory_survives_later_service_instance_for_same_identity():
    class Repository:
        value = None
        def get(self, **_): return self.value
        def observe(self, **_):
            from types import SimpleNamespace
            self.value = SimpleNamespace(preference_state={})
            return self.value
        def merge_conversational_memory(self, *, values, **_):
            from types import SimpleNamespace
            merged = {**dict(self.value.preference_state), **values}
            self.value = SimpleNamespace(preference_state=merged)
            return self.value
    repository = Repository()
    first = ConversationalMemoryService(repository=repository)
    first.learn(creator_profile_id=1, fanvue_account_id=2, telegram_user_id=3,
                telegram_chat_id=3, message_text="I'm from Tokyo")
    later = ConversationalMemoryService(repository=repository)
    facts = later.learn(creator_profile_id=1, fanvue_account_id=2, telegram_user_id=3,
                        telegram_chat_id=3, message_text="hey again")
    assert facts["timezone"] == "Asia/Tokyo"
    assert facts["memoryDiagnostics"]["identitySource"] == "TELEGRAM_NUMERIC_PROSPECT"
    recalled = ConversationalMemoryService.retrieve(
        repository.value.preference_state, "Where did I tell you I live?"
    )
    assert any(r["key"] == "location" and r["value"] == "Tokyo"
               for r in recalled["retrievedMemories"])


def test_sequence_one_memory_is_structured_without_phrase_specific_keys():
    observed = datetime(2026, 8, 26, 19, 20, tzinfo=timezone.utc)
    records = []
    timezone_name = None
    for message in (
        "I'm in Chicago, so I've still got a little afternoon left.",
        "Usually I'll take my dog Charlie for a walk. He's a golden retriever.",
        "I'm more of a hiking and camping person anyway. I'm actually taking Charlie to the vet Friday for his yearly checkup.",
        "I'm mostly into rock. Been listening to a lot of Foo Fighters lately.",
    ):
        extracted = ConversationalMemoryService.extract_records(
            message, observed_at=observed, customer_timezone=timezone_name)
        records.extend(extracted)
        timezone_record = next((r for r in extracted if r["key"] == "timezone"), None)
        if timezone_record: timezone_name = timezone_record["value"]
    assert any(r["key"] == "location" and r["value"] == "Chicago" for r in records)
    assert any(r["key"] == "timezone" and r["value"] == "America/Chicago" for r in records)
    charlie = next(r for r in records if r["category"] == "entity")
    assert charlie["value"]["name"] == "Charlie"
    assert charlie["value"]["breed"] == "golden retriever"
    assert {r["value"] for r in records if r["category"] == "preference"} >= {
            "hiking", "camping", "rock", "Foo Fighters"}
    event = next(r for r in records if r["category"] == "event")
    assert event["value"]["status"] == "upcoming"
    assert event["metadata"]["temporal"] is True


def test_ordinary_classifier_dictionary_keys_do_not_create_false_explicit_signal():
    ordinary = {"sexual_engagement": False, "explicit_without_buying_intent": False,
                "reason": "ordinary conversation"}
    assert DecisionEngine._explicit_request_detected("I live in Chicago", ordinary) is False
    assert DecisionEngine._explicit_request_detected("send explicit content", ordinary) is True
    assert DecisionEngine._explicit_request_detected(
        "hello", {"sexual_engagement": True}) is True


def test_location_correction_supersedes_prior_authority_and_events_age():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    first = datetime(2026, 8, 26, 19, tzinfo=timezone.utc)
    service._merge_records(state, service.extract_records("I'm in Chicago.", observed_at=first))
    service._merge_records(state, service.extract_records("I moved from Chicago to New York.", observed_at=first))
    current_locations = [r["value"] for r in state["records"]
                         if r["key"] == "location" and r["status"] == "current"]
    assert current_locations == ["New York"]
    assert any(r["key"] == "location" and r["status"] == "superseded"
               for r in state["records"])

    event = service.extract_records(
        "I'm taking Charlie to the vet Friday.", observed_at=first,
        customer_timezone="America/Chicago")[0]
    event_state = {"schemaVersion": 2, "records": [event]}
    service._refresh_event_lifecycle(event_state, datetime(2026, 8, 30, tzinfo=timezone.utc))
    assert event_state["records"][0]["value"]["status"] == "past"


def test_retrieval_selects_relevant_memory_instead_of_dumping_every_record():
    state = ConversationalMemoryService._normalize_state({})
    at = datetime(2026, 8, 26, tzinfo=timezone.utc)
    records = []
    for message in ("I'm in Chicago.", "My dog Charlie is a golden retriever.",
                    "I'm mostly into rock."):
        records += ConversationalMemoryService.extract_records(message, observed_at=at)
    ConversationalMemoryService._merge_records(state, records)
    result = ConversationalMemoryService.retrieve(state, "Charlie was wild today", now=at)
    assert any(r["key"] == "charlie" for r in result["retrievedMemories"])
    assert not any(r["key"] == "rock" for r in result["retrievedMemories"])


def test_activity_planning_retrieves_only_leisure_preferences_semantically():
    state = ConversationalMemoryService._normalize_state({})
    at = datetime(2026, 8, 26, tzinfo=timezone.utc)
    records = []
    for message in (
        "I’m more of a hiking and camping person.",
        "I'm mostly into rock. Been listening to a lot of Foo Fighters lately.",
        "My dog Charlie is a golden retriever.",
    ):
        records.extend(ConversationalMemoryService.extract_records(
            message, observed_at=at,
        ))
    ConversationalMemoryService._merge_records(state, records)

    planning_variants = (
        "Trying to decide what I should do this weekend if the weather’s nice",
        "Still deciding what to do this weekend if the weather holds up, any ideas for me?",
        "Still trying to figure out my weekend plans if the weather’s good, "
        "what do you think I should get into?",
        "Could you recommend some activities for my free time?",
        "I’ve got some free time this weekend if the weather cooperates - "
        "what sounds like something I’d be into?",
        "I've got Saturday free - what do you think I'd enjoy doing?",
        "What kind of weekend activity sounds up my alley?",
        "If I end up with a free afternoon this weekend, what sounds most like me?",
        "I've got a few hours to kill Saturday. What would suit me?",
        "What kind of thing would I actually enjoy doing outside?",
    )
    for message in planning_variants:
        result = ConversationalMemoryService.retrieve(state, message, now=at)
        assert {item["value"] for item in result["retrievedMemories"]} == {
            "hiking", "camping",
        }
        assert result["memoryDiagnostics"]["retrievedCategories"] == ["preference"]
        assert result["memoryDiagnostics"]["explicitRecallRequest"] is False
        assert not any(item["key"] in {
            "charlie", "rock", "music_artist_foo_fighters",
        } for item in result["retrievedMemories"])

    unrelated = ConversationalMemoryService.retrieve(
        state, "Long day at work", now=at,
    )
    assert unrelated["retrievedMemories"] == []

    unscoped_preference = ConversationalMemoryService.retrieve(
        state, "What sounds like something I'd be into?", now=at,
    )
    assert unscoped_preference["retrievedMemories"] == []

    music = ConversationalMemoryService.retrieve(
        state, "Any music suggestions for me?", now=at,
    )
    assert {item["value"] for item in music["retrievedMemories"]} >= {
        "rock", "Foo Fighters",
    }
    assert not any(item["value"] in {"hiking", "camping"}
                   for item in music["retrievedMemories"])

    personalized_music = ConversationalMemoryService.retrieve(
        state, "What kind of music do you think I'd like?", now=at,
    )
    assert {item["value"] for item in personalized_music["retrievedMemories"]} >= {
        "rock", "Foo Fighters",
    }
    assert not any(item["value"] in {"hiking", "camping"}
                   for item in personalized_music["retrievedMemories"])

    taste_music = ConversationalMemoryService.retrieve(
        state, "Give me something to listen to that fits my taste.", now=at,
    )
    assert {item["value"] for item in taste_music["retrievedMemories"]} >= {
        "rock", "Foo Fighters",
    }
    band = ConversationalMemoryService.retrieve(
        state, "What band have I been into?", now=at,
    )
    assert any(item["value"] == "Foo Fighters" for item in band["retrievedMemories"])
    assert ConversationalMemoryService.retrieve(
        state, "Tell me something.", now=at,
    )["retrievedMemories"] == []


def test_actual_generation_prompt_receives_canonical_time_memory_and_style_contract():
    class Training:
        def runtime_prompt_block(self, **_): return ""
    class Completions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return type("Completion", (), {"choices": [type("Choice", (), {
                "message": type("Message", (), {"content": "Still afternoon for me."})()
            })()]})()
    captured = {}
    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = type("Client", (), {"chat": type("Chat", (), {
        "completions": Completions()})()})()
    result = service.generate_response("default", "casual", "How's your night?", {
        "runtime_injection": {"time_context": {
            "avaTimezone": "America/New_York", "avaDaypart": "afternoon",
            "avaLocalTime": "2026-08-26T15:14:00-04:00",
            "customerTimezone": "America/Chicago",
        }, "conversational_memory": {"timezone": "America/Chicago",
            "retrievedMemories": [{"key": "charlie", "value": {"name": "Charlie"}}],
            "memoryDiagnostics": {"explicitRecallRequest": True, "recallSatisfied": True}}},
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }, False, chat_history=[])
    prompt = captured["messages"][0]["content"]
    assert result == "Still afternoon for me."
    assert '"avaDaypart": "afternoon"' in prompt
    assert '"name": "Charlie"' in prompt
    assert "customer saying \"night\" does not make it night for Ava" in prompt
    assert "A question is optional" in prompt
    assert "never invent a customer fact" in prompt
    assert "Treat only retrievedMemories as recall evidence" in prompt


def test_controlled_unmapped_recall_selects_entity_preferences_and_event():
    state = ConversationalMemoryService._normalize_state({})
    at = datetime(2026, 8, 26, 14, 20, tzinfo=timezone.utc)
    records = []
    for message in (
        "My dog Charlie is a golden retriever.",
        "I'm mostly into rock. Been listening to a lot of Foo Fighters lately.",
        "I'm taking Charlie to the vet Friday for his yearly checkup.",
    ):
        records.extend(ConversationalMemoryService.extract_records(
            message, observed_at=at, customer_timezone="America/Chicago"))
    ConversationalMemoryService._merge_records(state, records)

    dog = ConversationalMemoryService.retrieve(
        state, "Remind me, what kind of dog did I tell you Charlie is?", now=at)
    assert [r["key"] for r in dog["retrievedMemories"]][0] == "charlie"
    assert dog["retrievedMemories"][0]["value"]["breed"] == "golden retriever"
    assert dog["memoryDiagnostics"]["explicitRecallRequest"] is True
    assert dog["memoryDiagnostics"]["recallSatisfied"] is True

    music = ConversationalMemoryService.retrieve(
        state, "You remember what kind of music I'm into?", now=at)
    assert {r["value"] for r in music["retrievedMemories"]} >= {"rock", "Foo Fighters"}

    event = ConversationalMemoryService.retrieve(
        state, "Charlie's gonna be spoiled after Friday", now=at)
    assert any(r["category"] == "event" and "vet" in r["value"]["summary"]
               for r in event["retrievedMemories"])

    direct_event = ConversationalMemoryService.retrieve(
        state, "What am I doing with Charlie Friday?", now=at)
    assert any(r["category"] == "event" and "vet" in r["value"]["summary"]
               for r in direct_event["retrievedMemories"])

    irrelevant = ConversationalMemoryService.retrieve(
        state, "Long day at work", now=at)
    assert irrelevant["retrievedMemories"] == []


def test_missing_explicit_recall_sets_fail_closed_prompt_contract():
    result = ConversationalMemoryService.retrieve(
        {"schemaVersion": 2, "records": []},
        "Remind me what my favorite color is",
    )
    assert result["memoryDiagnostics"]["explicitRecallRequest"] is True
    assert result["memoryDiagnostics"]["recallSatisfied"] is False


def test_natural_recall_language_is_detected_without_customer_specific_values():
    recall_messages = (
        "what breed is Charlie?",
        "what kind of dog did I tell you Charlie is?",
        "you remember what music I like?",
        "what did I tell you about Charlie?",
        "do you remember where I live?",
        "what was that thing I said was happening Friday?",
        "Okay, no guessing this time - what is it?",
    )
    for message in recall_messages:
        result = ConversationalMemoryService.retrieve(
            {"schemaVersion": 2, "records": []}, message,
        )
        assert result["memoryDiagnostics"]["explicitRecallRequest"] is True
        assert result["memoryDiagnostics"]["recallSatisfied"] is False


def test_gateway_preserves_live_telegram_memory_context_before_generation():
    supplied_memory = {
        "retrievedMemories": [{"category": "entity", "key": "pet_name", "value": {
            "name": "Example", "breed": "retrieved breed"}}],
        "memoryDiagnostics": {
            "retrievalAttempted": True,
            "identitySource": "TELEGRAM_NUMERIC_PROSPECT",
            "explicitRecallRequest": True,
            "retrievedCount": 1,
            "retrievedKeys": ["pet_name"],
            "retrievedCategories": ["entity"],
            "recallSatisfied": True,
        },
    }
    gateway = ConversationGateway(
        object(), allowed_fanvue_hostnames=["fanvue.com"], creator_profile_id=2,
    )
    context = gateway._brain_context(ConversationGatewayInput(
        engine_user_id="2:-123", message_text="what breed is the pet?",
        chat_history=[], correlation_id="telegram:123:1",
        brain_context=ConversationBrainContext(
            creator_profile_id=2, customer_identifier="2:-123",
            conversation_identifier="telegram:123:1", telegram_user_id=123,
            telegram_chat_id=123, fanvue_account_id=2,
            conversational_memory=supplied_memory,
        ),
    ))
    assert context.telegram_user_id == 123
    assert context.telegram_chat_id == 123
    assert context.conversational_memory == supplied_memory
    assert context.conversational_memory is not supplied_memory


def test_supervised_private_chat_entry_injects_activity_memory_for_unmapped_prospect():
    class ProspectRepository:
        def __init__(self):
            self.row = type("Prospect", (), {"preference_state": {
                "schemaVersion": 2,
                "records": [ConversationalMemoryService._record(
                    "entity", "sample_pet",
                    {"name": "Sample", "type": "dog", "breed": "retrieved breed"},
                    "customer-provided fixture", datetime.now(timezone.utc),
                ), ConversationalMemoryService._record(
                    "preference", "hiking", "hiking",
                    "I'm more of a hiking and camping person.",
                    datetime.now(timezone.utc), .9,
                    {"domain": "leisure_activity"},
                ), ConversationalMemoryService._record(
                    "preference", "camping", "camping",
                    "I'm more of a hiking and camping person.",
                    datetime.now(timezone.utc), .9,
                    {"domain": "leisure_activity"},
                )],
            }})()
        def get(self, **_): return self.row
        def observe(self, **_): return self.row
        def merge_conversational_memory(self, *, values, **_):
            self.row.preference_state = values
            return self.row

    class Engine:
        def __init__(self): self.injection = None
        def process_message(self, user_id, message, chat_history=None,
                            runtime_injection=None):
            self.injection = runtime_injection
            return {"response": "fixture reply", "send_offer": False,
                    "offer": {"offer_type": "none", "content": None}}

    engine = Engine()
    gateway = ConversationGateway(
        engine, allowed_fanvue_hostnames=["fanvue.com"], creator_profile_id=2,
    )
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=gateway, creator_profile_id=2, fanvue_account_id=2,
        conversational_memory_service=ConversationalMemoryService(
            repository=ProspectRepository()),
    )
    with patch(
        "app.services.private_chat_unlock_gateway_service.fingerprint_bootstrap_enabled",
        return_value=False,
    ):
        result = adapter.execute(TelegramInboundPayload(
            telegram_user_id=123, telegram_chat_id=123,
            message_text=("If I end up with a free afternoon this weekend, "
                          "what sounds most like me?"),
            message_id=1,
        ))

    memory = engine.injection["conversational_memory"]
    assert {item["value"] for item in memory["retrievedMemories"]} == {
        "hiking", "camping",
    }
    assert not any(item["key"] == "sample_pet" for item in memory["retrievedMemories"])
    assert memory["memoryDiagnostics"]["identitySource"] == "TELEGRAM_NUMERIC_PROSPECT"
    diagnostics = result.diagnostic_metadata["conversational_memory"]
    assert diagnostics.items() >= {
        "retrievalAttempted": True,
        "identitySource": "TELEGRAM_NUMERIC_PROSPECT",
        "available": True,
        "relevantMemoriesFound": True,
        "retrievedCount": 2,
        "retrievedKeys": ["hiking", "camping"],
        "retrievedCategories": ["preference"],
        "semanticClassificationAttempted": True,
        "semanticDomains": ["leisure_activity"],
        "semanticClassificationConfidence": .9,
        "semanticClassificationSource": "DETERMINISTIC_SEMANTIC_FEATURES",
        "explicitRecallRequest": False,
        "recallSatisfied": None,
        "injectedIntoGeneration": True,
        "commerceMemorySource": None,
        "separateFromCommerceMemory": True,
    }.items()
    assert diagnostics["persistenceSource"] == (
        "telegram_sales_prospects.preference_state"
    )
    assert diagnostics["retrievalSource"] == (
        "telegram_sales_prospects.preference_state"
    )
