from dataclasses import replace
from types import SimpleNamespace

from app.services.customer_content_presentation_validator import (
    CustomerContentPresentationValidator,
)
from app.services.photoshoot_session_conversation_context_builder import (
    PhotoshootSessionConversationContextBuilder,
)
from app.test_photoshoot_session_conversation_context import action_with_runtime


class SessionStrategies:
    def latest(self, _):
        roles = (
            (20, "FREE_TEASER", "FREE"),
            (21, "FIRST_UNLOCK", "PAID"),
            (22, "ESCALATION", "PAID"),
            (23, "PREMIUM", "PAID"),
            (24, "FINALE", "PAID"),
        )
        return SimpleNamespace(shots=tuple(
            SimpleNamespace(
                asset_id=asset_id, sales_role=role,
                access_recommendation=access,
                customer_journey_purpose=f"Purpose for {role}",
                recommended_progression=f"Progress through {role}",
            ) for asset_id, role, access in roles
        ))


class SessionPhotoshoots:
    def get_by_session(self, _): return {"display_name": "Evening Story"}
    def get_intelligence(self, _):
        return {"theme": "Evening", "story": "A gradual progression", "profile_data": {}}
    def latest_shot_intelligence(self, _):
        return tuple({
            "asset_id": asset_id,
            "profile_data": {
                "sequence_role": role.lower(),
                "scene_environment": "studio",
                "emotional_tone": "confident",
            },
        } for asset_id, role in (
            (20, "FREE_TEASER"), (21, "FIRST_UNLOCK"),
            (22, "ESCALATION"), (23, "PREMIUM"), (24, "FINALE"),
        ))


def session_context(role, asset_id, position, owned=()):
    action = action_with_runtime(role)
    runtime = dict(action.metadata["sessionRuntime"])
    runtime.update({
        "currentSalesRole": role, "currentAssetId": asset_id,
        "currentPosition": position, "totalPositions": 5,
        "ownedAssetIds": list(owned),
        "nextAssetId": None if role == "FINALE" else asset_id + 1,
        "nextSalesRole": None if role == "FINALE" else "CONTINUATION",
    })
    action = replace(action, selected_asset_id=asset_id,
                     metadata={"sessionRuntime": runtime})
    return PhotoshootSessionConversationContextBuilder(
        strategies=SessionStrategies(), photoshoots=SessionPhotoshoots(),
    ).build(SimpleNamespace(next_sales_action=action))


def test_session_roles_receive_human_progression_and_owned_step_continuity():
    first = session_context("FIRST_UNLOCK", 21, 2, owned=(20,))
    assert first["progressionAwareness"] == {
        "currentRole": "FIRST_UNLOCK", "currentPaidStep": 1,
        "totalPaidSteps": 4, "previousPaidUnlocks": 0,
        "remainingAfterCurrent": 3, "sessionTeaserPreviouslyShown": True,
        "continuityInstruction": first["progressionAwareness"]["continuityInstruction"],
    }
    escalation = session_context("ESCALATION", 22, 3, owned=(20, 21))
    premium = session_context("PREMIUM", 23, 4, owned=(20, 21, 22))
    finale = session_context("FINALE", 24, 5, owned=(20, 21, 22, 23))
    assert escalation["progressionAwareness"]["previousPaidUnlocks"] == 1
    assert premium["progressionAwareness"]["previousPaidUnlocks"] == 2
    assert finale["progressionAwareness"]["previousPaidUnlocks"] == 3
    assert finale["progressionAwareness"]["remainingAfterCurrent"] == 0
    assert finale["nextStep"]["salesRole"] is None
    assert "culmination" in finale["boundaries"]["message_objective"]


def test_bundle_count_and_session_role_contradictions_fail_closed():
    validator = CustomerContentPresentationValidator()
    offering = SimpleNamespace(price_minor=1499)
    bundle = {"bundleOffer": {"paidMemberCount": 8}}
    assert not validator.validate_paid(
        "I put all 15 photos together for you.", offering=offering,
        presentation_context={"bundle": bundle},
    ).valid
    finale = {"progressionAwareness": {
        "currentRole": "FINALE", "remainingAfterCurrent": 0,
    }}
    result = validator.validate_paid(
        "Wait until you see the next one.", offering=offering,
        presentation_context={"session": finale},
    )
    assert result.reason == "PAID_PRESENTATION_FINALE_CONTINUATION_CLAIM"
    first = {"progressionAwareness": {
        "currentRole": "FIRST_UNLOCK", "previousPaidUnlocks": 0,
    }}
    result = validator.validate_paid(
        "You loved all those previous paid steps.", offering=offering,
        presentation_context={"session": first},
    )
    assert result.reason == "PAID_PRESENTATION_FALSE_SESSION_HISTORY"


def test_short_grounded_finale_language_remains_valid():
    result = CustomerContentPresentationValidator().validate_paid(
        "Okay... this is the payoff I was saving for you 😏",
        offering=SimpleNamespace(price_minor=1499),
        presentation_context={"session": {"progressionAwareness": {
            "currentRole": "FINALE", "remainingAfterCurrent": 0,
        }}},
    )
    assert result.valid is True
