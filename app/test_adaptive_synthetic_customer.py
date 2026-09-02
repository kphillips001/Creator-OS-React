from app.testing.adaptive_synthetic_customer import (
    AdaptiveSyntheticCustomerService, CustomerBehaviorPhase,
)


def make(phase, ava, *, scenario="C02", reaction="NONE", generator=None,
         facts=(), buyer="UNCHANGED", transcript=(), offer_context=None):
    service = AdaptiveSyntheticCustomerService(generator=generator)
    constraints = service.constraints_for(
        scenario, phase, offer_reaction=reaction,
        disclosed_facts=facts, fixture_buyer_state=buyer,
    )
    return service.generate_turn(
        scenario_id=scenario, scenario_attempt=99, logical_turn=2,
        phase=phase, constraints=constraints, previous_ava_response=ava,
        recent_transcript=transcript,
        phase_transition_reason="CERTIFICATION_TRAJECTORY",
        authoritative_offer_context=offer_context,
    )


def test_quiet_customer_answers_actual_question_coherently_and_stays_terse():
    result = make(CustomerBehaviorPhase.QUIET_LOW_RETURN, "What are you up to tonight?")
    assert result.final_customer_message == "not much honestly"
    assert result.previous_ava_response == "What are you up to tonight?"
    assert result.customer_constraints["engagement"] == "LOW"
    assert result.validation_result["derivedSignals"]["buyingIntent"] is False


def test_quiet_customer_can_answer_statement_without_inventing_engagement():
    result = make(CustomerBehaviorPhase.QUIET_LOW_RETURN, "I'm just relaxing tonight.")
    assert result.final_customer_message == "yeah just scrolling"
    assert result.customer_constraints["reciprocity"] == "LOW"


def test_attraction_does_not_blur_into_buying_intent():
    result = make(CustomerBehaviorPhase.ATTRACTION, "You’re trouble lol")
    assert "hot" in result.final_customer_message
    assert result.validation_result["derivedSignals"]["buyingIntent"] is False
    assert result.customer_constraints["buying_intent"] is False


def test_commercial_curiosity_can_request_content_without_buying():
    result = make(CustomerBehaviorPhase.COMMERCIAL_CURIOSITY, "Maybe I can keep you entertained.")
    assert "private" in result.final_customer_message
    assert result.validation_result["derivedSignals"]["contentInterest"] is True
    assert result.validation_result["derivedSignals"]["buyingIntent"] is False


def test_buying_phase_expresses_genuine_buying_interest():
    result = make(CustomerBehaviorPhase.BUYING_INTEREST, "I might have something you'd like.")
    assert "how much" in result.final_customer_message
    assert result.validation_result["derivedSignals"]["buyingIntent"] is True
    assert result.customer_constraints["buying_intent"] is True


def test_offer_reaction_uses_actual_price_for_hesitation():
    result = make(CustomerBehaviorPhase.OFFER_REACTION,
                  "I have a private set for $9 — tap unlock if you want it.", reaction="HESITATE")
    assert "$9" in result.final_customer_message
    assert result.validation_result["derivedSignals"]["offerAcceptance"] is False


def test_customer_cannot_reference_unsupplied_price():
    result = make(CustomerBehaviorPhase.BUYING_INTEREST, "I have something private.",
                  generator=lambda _: "$9 works for me")
    assert result.wording_source == "DETERMINISTIC_PHASE_SAFE_FALLBACK_AFTER_REJECTION"
    assert "$9" not in result.final_customer_message


def test_customer_cannot_accept_an_offer_that_does_not_exist():
    result = make(CustomerBehaviorPhase.OFFER_REACTION, "What are you looking for?",
                  reaction="ACCEPT")
    assert result.final_customer_message is None
    assert "OFFER_REACTION_WITHOUT_ACTUAL_OFFER" in result.blocked_reason


def structured_ppv(price="$19.00"):
    return {
        "offeringId": "offering-19", "name": "Private Single",
        "type": "SINGLE_IMAGE", "price": price, "priceMinor": 1900,
        "currency": "USD", "channel": "AI_CHAT",
        "cta": {"label": "Unlock", "target": "SYNTHETIC_PRIVATE_CHAT_UNLOCK"},
        "purchaseIntent": {"id": "intent-19", "state": "CREATED"},
    }


def test_structured_ppv_authorizes_exact_price_hesitation():
    result = make(
        CustomerBehaviorPhase.OFFER_REACTION,
        "I've got this one for you — unlock it when you're ready.",
        reaction="HESITATE", offer_context=structured_ppv(),
    )
    assert result.final_customer_message == "hmm, $19.00 is more than I expected"
    assert result.validation_result["valid"] is True
    assert result.authoritative_offer_context["authority"] == "SYNTHETIC_PPV_PRESENTATION"
    assert result.authoritative_offer_context["purchaseIntentId"] == "intent-19"


def test_structured_ppv_keeps_hesitation_distinct_from_acceptance():
    result = make(
        CustomerBehaviorPhase.OFFER_REACTION, "unlock it when you're ready",
        reaction="HESITATE", offer_context=structured_ppv(),
    )
    assert result.validation_result["derivedSignals"]["offerAcceptance"] is False


def test_structured_ppv_allows_scenario_controlled_acceptance():
    result = make(
        CustomerBehaviorPhase.OFFER_REACTION, "unlock it when you're ready",
        reaction="ACCEPT", offer_context=structured_ppv(),
    )
    assert result.final_customer_message == "alright yeah, send it"
    assert result.validation_result["derivedSignals"]["offerAcceptance"] is True


def test_structured_ppv_rejects_invented_different_price():
    result = make(
        CustomerBehaviorPhase.OFFER_REACTION, "unlock it when you're ready",
        reaction="HESITATE", offer_context=structured_ppv(),
        generator=lambda _: "$9 is more than I expected",
    )
    assert result.generated_customer_candidate == "$9 is more than I expected"
    assert "CUSTOMER_REFERENCED_DIFFERENT_PRICE" in result.validation_result[
        "generatedCandidateValidation"
    ]["reasons"]
    assert "$19.00" in result.final_customer_message


def test_poor_ava_termination_does_not_get_rescued():
    result = make(CustomerBehaviorPhase.COMMERCIAL_CURIOSITY, "Leave me alone.")
    assert result.final_customer_message is None
    assert result.wording_source == "BLOCKED"


def test_scenario_phase_rejects_generator_commercial_drift():
    result = make(CustomerBehaviorPhase.QUIET_LOW_RETURN, "How’s your night?",
                  generator=lambda _: "I'll buy your private pics")
    assert result.customer_constraints["buying_intent"] is False
    assert result.final_customer_message == "idk honestly"
    assert result.wording_source == "DETERMINISTIC_PHASE_SAFE_FALLBACK_AFTER_REJECTION"
    assert result.generated_customer_candidate == "I'll buy your private pics"
    assert "WORDING_INTRODUCED_BUYING_INTENT" in result.validation_result[
        "generatedCandidateValidation"
    ]["reasons"]


def test_truthful_build_interest_response_keeps_reveal_phase_reachable():
    result = make(
        CustomerBehaviorPhase.REVEAL_INTEREST,
        "mm maybe just a little more... can't give away all the fun yet",
        scenario="C07",
        generator=lambda _: (
            "okay now I'm really curious... what exactly are you teasing?"
        ),
    )

    assert result.final_customer_message is not None
    assert result.validation_result["valid"] is True
    assert "WORDING_INTRODUCED_BUYING_INTENT" not in result.validation_result[
        "reasons"
    ]


def test_c07_reveal_fallback_remains_nonbuying_and_nonsexual():
    result = make(
        CustomerBehaviorPhase.REVEAL_INTEREST,
        "Maybe I’m just getting started—wait till you see what’s next.",
        scenario="C07",
    )

    assert result.final_customer_message is not None
    assert result.validation_result["valid"] is True
    signals = result.validation_result["derivedSignals"]
    assert signals["buyingIntent"] is False
    assert signals["sexualInterestIntensity"] == "MILD_OR_NONE"
    assert "WORDING_INTRODUCED_BUYING_INTENT" not in result.validation_result[
        "reasons"
    ]


def test_talkative_and_rude_scenario_styles_remain_distinct():
    talkative = make(CustomerBehaviorPhase.QUIET_LOW_RETURN, "What are you doing?", scenario="C07")
    rude = make(CustomerBehaviorPhase.ATTRACTION, "You’re bold.", scenario="C03")
    assert len(talkative.final_customer_message.split()) > 8
    assert rude.customer_constraints["friendliness"] == "RUDE"
    assert "at least" in rude.final_customer_message


def test_attraction_phase_rejects_wording_without_attraction():
    result = make(
        CustomerBehaviorPhase.ATTRACTION,
        "You think you're interesting?",
        scenario="C03",
        generator=lambda _prompt: (
            "Don't come back unless you've got something worth my time."
        ),
    )
    assert result.generated_customer_candidate is not None
    assert "ATTRACTION_PHASE_WITHOUT_ATTRACTION" in (
        result.validation_result["generatedCandidateValidation"]["reasons"]
    )


def test_fixture_buyer_truth_facts_and_recent_transcript_are_preserved():
    transcript = ({"role": "customer", "content": "I live in Chicago"},
                  {"role": "ava", "content": "Chicago sounds fun"})
    result = make(CustomerBehaviorPhase.BUYING_INTEREST, "Want to see something private?",
                  scenario="C16", facts=("location=Chicago",), buyer="WHALE", transcript=transcript)
    assert result.customer_constraints["fixture_buyer_state"] == "WHALE"
    assert result.customer_constraints["disclosed_facts"] == ("location=Chicago",)
    assert result.recent_transcript == transcript


def test_generated_customer_cannot_contradict_disclosed_location():
    result = make(CustomerBehaviorPhase.ATTRACTION, "Tell me something about you.",
                  facts=("location=Chicago",), generator=lambda _: "I live in Miami")
    assert result.final_customer_message == "you look pretty hot though"
    assert "CUSTOMER_FACT_CONTRADICTED_LOCATION" in result.validation_result[
        "generatedCandidateValidation"
    ]["reasons"]


def test_generator_receives_recent_transcript_without_hidden_reasoning():
    seen = {}
    transcript = ({"role": "customer", "content": "not much"},
                  {"role": "ava", "content": "same here"})
    def generator(prompt):
        seen.update(prompt)
        return "yeah just scrolling"
    result = make(CustomerBehaviorPhase.QUIET_LOW_RETURN, "I'm taking it easy.",
                  transcript=transcript, generator=generator)
    assert seen["recentTranscript"] == transcript
    assert result.provider_metadata["hiddenReasoningPersisted"] is False


def test_audit_is_structured_and_contains_no_hidden_reasoning():
    result = make(CustomerBehaviorPhase.ATTRACTION, "You’re making me blush.")
    audit = result.to_mapping()
    assert audit["behavioral_phase"] == "ATTRACTION"
    assert audit["provider_metadata"]["hiddenReasoningPersisted"] is False
    assert audit["validation_result"]["structuredTruthUnchanged"] is True


def test_c05_requires_high_attraction_and_high_sexual_interest_without_commerce():
    result = make(
        CustomerBehaviorPhase.ATTRACTION, "hey you",
        scenario="C05", generator=lambda _: "you look hot but that's all",
    )
    generated = result.validation_result["generatedCandidateValidation"]
    assert "REQUIRED_HIGH_SEXUAL_INTEREST_NOT_EXPRESSED" in generated["reasons"]
    assert result.validation_result["derivedSignals"]["sexualInterestIntensity"] == "HIGH"
    assert result.validation_result["derivedSignals"]["runtimeSexualOrProvocative"] is True
    assert result.validation_result["derivedSignals"]["buyingIntent"] is False
    assert result.validation_result["derivedSignals"]["contentInterest"] is False


def test_c05_strong_noncommercial_sexual_interest_provider_candidate_can_pass():
    result = make(
        CustomerBehaviorPhase.ATTRACTION, "you're trouble",
        scenario="C05",
        generator=lambda _: "you look hot and you're making my thoughts dirty",
    )
    assert result.wording_source == "PROVIDER"
    assert result.validation_result["valid"] is True
    signals = result.validation_result["derivedSignals"]
    assert signals["sexualInterestIntensity"] == "HIGH"
    assert signals["runtimeSexualOrProvocative"] is True
    assert signals["buyingIntent"] is False
    assert signals["contentInterest"] is False


def test_c05_high_sexual_interest_cannot_introduce_price_or_purchase_request():
    result = make(
        CustomerBehaviorPhase.ATTRACTION, "you're trouble",
        scenario="C05",
        generator=lambda _: "you look hot and make my thoughts dirty, how much to unlock?",
    )
    reasons = result.validation_result["generatedCandidateValidation"]["reasons"]
    assert "WORDING_INTRODUCED_BUYING_INTENT" in reasons
    assert "ATTRACTION_PHASE_BLURRED_COMMERCIAL_TRUTH" in reasons
    assert result.validation_result["derivedSignals"]["buyingIntent"] is False


def test_c05_fallback_preserves_intensity_and_varies_against_recent_customer_wording():
    first = make(CustomerBehaviorPhase.ATTRACTION, "hey", scenario="C05")
    transcript = (
        {"role": "customer", "content": first.final_customer_message},
        {"role": "ava", "content": "careful, you're trouble"},
    )
    second = make(
        CustomerBehaviorPhase.ATTRACTION, "careful, you're trouble",
        scenario="C05", transcript=transcript,
    )
    assert first.final_customer_message != second.final_customer_message
    assert second.validation_result["valid"] is True
    assert second.validation_result["derivedSignals"]["runtimeSexualOrProvocative"] is True


def test_c05_trajectory_guard_uses_canonical_runtime_tone_projection():
    aligned = make(
        CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        "maybe I have a private side you haven't seen",
        scenario="C05", generator=lambda _prompt: (
            "you're turning me on now, tease me about that private side"
        ),
    )
    assert aligned.validation_result["valid"] is True
    assert aligned.validation_result["trajectorySexualAlignmentRequired"] is True
    assert aligned.validation_result["trajectorySexualAlignmentSatisfied"] is True
    assert aligned.validation_result["trajectorySexualAlignmentSource"] == (
        "ContextualCustomerToneService.sexualOrProvocative"
    )

    nonaligned = make(
        CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        "maybe I have a private side you haven't seen",
        scenario="C05", generator=lambda _prompt: "give me a little hint",
    )
    generated = nonaligned.validation_result["generatedCandidateValidation"]
    assert generated["trajectorySexualAlignmentRequired"] is True
    assert generated["trajectorySexualAlignmentSatisfied"] is False
    assert "RUNTIME_SEXUAL_PROVOCATIVE_ALIGNMENT_MISSING" in generated["reasons"]


def test_provider_receives_explicit_intensity_and_repetition_fidelity_contract():
    seen = {}
    transcript = ({"role": "customer", "content": "you look hot"},)
    result = make(
        CustomerBehaviorPhase.ATTRACTION, "mm careful",
        scenario="C05", transcript=transcript,
        generator=lambda prompt: seen.update(prompt) or (
            "you look hot and you're making my thoughts dirty"
        ),
    )
    fidelity = seen["fidelityRequirements"]
    assert fidelity["expressAttractionIntensity"] == "HIGH"
    assert fidelity["expressSexualInterestIntensity"] == "HIGH"
    assert fidelity["commercialCuriosityMustRemain"] == "NONE"
    assert fidelity["buyingIntentMustRemain"] is False
    assert fidelity["avoidRecentCustomerWording"] == ["you look hot"]
    assert result.validation_result["valid"] is True


def test_compositional_c05_fallback_sustains_more_than_two_distinct_turns():
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.ATTRACTION
    constraints = service.constraints_for("C05", phase)
    transcript = []
    messages = []
    ava_messages = (
        "careful, what are you imagining?",
        "mm you're trouble",
        "that's a bold thing to say",
        "you really aren't behaving tonight",
        "I can tell where your mind is going",
    )
    for logical_turn, ava in enumerate(ava_messages, 1):
        result = service.generate_turn(
            scenario_id="C05", scenario_attempt=1, logical_turn=logical_turn,
            phase=phase, constraints=constraints, previous_ava_response=ava,
            recent_transcript=tuple(transcript[-6:]),
            phase_transition_reason="SEXUAL_ONLY_CONTINUATION",
        )
        assert result.final_customer_message is not None
        assert result.validation_result["valid"] is True
        assert result.validation_result["derivedSignals"]["buyingIntent"] is False
        assert result.validation_result["derivedSignals"]["contentInterest"] is False
        messages.append(result.final_customer_message)
        transcript.extend((
            {"role": "customer", "content": result.final_customer_message},
            {"role": "ava", "content": ava},
        ))
    assert len(set(messages)) == len(messages)
