from types import MappingProxyType, SimpleNamespace

from app.services.ownership_decision_projection import OwnershipDecisionProjection


class FakeOwnershipIntelligence:
    def __init__(self, answer=None, error=None):
        self.answer_value = answer
        self.error = error

    def answer(self, identity):
        if self.error:
            raise self.error
        return self.answer_value

    @staticmethod
    def owns_asset(answer, asset_id):
        return asset_id in answer.owned_asset_ids


def answer(*, assets=(), tag=None, conflicts=(), insufficiencies=()):
    evidence = () if tag is None else (
        SimpleNamespace(
            proves_ownership=True,
            details=MappingProxyType({"contentTag": tag}),
        ),
    )
    return SimpleNamespace(
        owned_asset_ids=tuple(assets), evidence=evidence,
        conflicts=tuple(conflicts), insufficiencies=tuple(insufficiencies),
    )


def projection(value):
    return OwnershipDecisionProjection(
        ownership_intelligence=FakeOwnershipIntelligence(value),
        creator_profile_resolver=lambda _account: {"id": 7},
    )


def test_owned_asset_and_content_tag_block_through_canonical_answer():
    service = projection(answer(assets=(101,), tag="vip-set"))

    assert service.asset(
        fanvue_account_id=2, fanvue_user_id=3, asset_id=101,
    ).blocks_offer
    assert service.content_tag(
        fanvue_account_id=2, fanvue_user_id=3, content_tag="VIP-SET",
    ).blocks_offer


def test_no_demonstrated_ownership_does_not_block():
    decision = projection(answer()).asset(
        fanvue_account_id=2, fanvue_user_id=3, asset_id=101,
    )

    assert not decision.owned
    assert not decision.fail_closed
    assert not decision.blocks_offer


def test_conflict_and_insufficiency_fail_closed():
    conflict = projection(answer(conflicts=("SOURCE_CONFLICT",))).asset(
        fanvue_account_id=2, fanvue_user_id=3, asset_id=101,
    )
    insufficient = projection(answer(insufficiencies=("SOURCE_DOWN",))).asset(
        fanvue_account_id=2, fanvue_user_id=3, asset_id=101,
    )

    assert conflict.fail_closed and conflict.blocks_offer
    assert insufficient.fail_closed and insufficient.blocks_offer


def test_missing_creator_scope_fails_closed_without_querying_sources():
    service = OwnershipDecisionProjection(
        ownership_intelligence=FakeOwnershipIntelligence(error=AssertionError()),
        creator_profile_resolver=lambda _account: None,
    )

    decision = service.asset(
        fanvue_account_id=2, fanvue_user_id=3, asset_id=101,
    )

    assert decision.fail_closed
    assert decision.insufficiencies == ("OWNERSHIP_IDENTITY_INSUFFICIENT",)
