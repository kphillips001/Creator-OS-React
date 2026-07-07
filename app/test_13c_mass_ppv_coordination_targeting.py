from app.services.mass_ppv_targeting_service import MassPPVTargetingService


class FakeBlockedCoordinationService:
    def evaluate(self, user_memory: dict) -> dict:
        return {
            "allow_outreach": False,
            "allow_mass_ppv": False,
            "mass_ppv_priority": "blocked",
            "recommended_action": "protect_user",
        }


class FakeAllowedCoordinationService:
    def evaluate(self, user_memory: dict) -> dict:
        return {
            "allow_outreach": False,
            "allow_mass_ppv": True,
            "mass_ppv_priority": "normal",
            "recommended_action": "stop_outreach_keep_mass_ppv",
        }


class FakeRealtimeBuyerStateService:
    def get_buyer_state(self, fanvue_account_id: int, fanvue_user_id: int) -> dict:
        return {
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
        }

    def is_eligible_for_mass_ppv(self, realtime_state: dict) -> dict:
        return {
            "allowed": True,
            "block_reason": None,
        }


class FakeContentOwnershipService:
    def user_already_owns_content(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        content_tag: str,
    ) -> bool:
        return False


class FakePriorityService:
    def can_enter_monetization_flow(
        self,
        user_memory: dict,
        source: str,
        fanvue_user: dict,
    ) -> dict:
        return {
            "allowed": True,
            "reason": "test_allowed",
        }

    def log_monetization_decision(
        self,
        source: str,
        user_id,
        username,
        result: dict,
        user_memory: dict,
    ) -> None:
        return None


def build_service():
    service = MassPPVTargetingService()
    service._is_mass_ppv_enabled = lambda: True
    service.realtime_buyer_state_service = FakeRealtimeBuyerStateService()
    service.content_ownership_service = FakeContentOwnershipService()
    service.priority_service = FakePriorityService()
    return service


def main():
    print("\n=== 13C MASS PPV COORDINATION TARGETING TEST ===\n")

    fanvue_user = {
        "id": 101,
        "fanvue_account_id": 1,
        "username": "test_user",
        "is_subscriber": False,
    }

    memory = {
        "fanvue_user_id": 101,
        "fanvue_account_id": 1,
        "user_value_tier": "low",
        "buyer_tier": "low",
    }

    service = build_service()
    service.outreach_mass_ppv_coordination_service = (
        FakeBlockedCoordinationService()
    )

    allowed, reason = service.is_user_eligible_for_mass_ppv(
        fanvue_user=fanvue_user,
        memory=memory,
        content_tag="TEST_CONTENT",
    )

    print("Blocked coordination result:", allowed, reason)

    assert allowed is False
    assert reason == "outreach_mass_ppv_coordination:protect_user"

    service = build_service()
    service.outreach_mass_ppv_coordination_service = (
        FakeAllowedCoordinationService()
    )

    allowed, reason = service.is_user_eligible_for_mass_ppv(
        fanvue_user=fanvue_user,
        memory=memory,
        content_tag="TEST_CONTENT",
    )

    print("Allowed coordination result:", allowed, reason)

    assert allowed is True
    assert reason == "follower_or_non_subscriber"

    print("\n✅ 13C MASS PPV COORDINATION TARGETING TEST PASSED\n")


if __name__ == "__main__":
    main()