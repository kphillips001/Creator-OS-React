from app.repositories.qualification_ppv_repository import (
    create_qualification_ppv_event,
)


class FollowerWelcomeService:

    """
    3D.10.3

    Handles new follower qualification flows.
    """

    def create_follower_welcome_offer(
        self,
        *,
        fanvue_user_id: str,
        fanvue_account_id: str,
    ):

        qualification_event = (
            create_qualification_ppv_event(
                fanvue_user_id=fanvue_user_id,
                fanvue_account_id=fanvue_account_id,
                qualification_type="FOLLOWER_WELCOME",
                content_tag="FOLLOWER_WELCOME_PPV",
                fanvue_media_uuid="follower_media_001",
                price=5.00,
            )
        )

        return {
            "success": True,
            "fanvue_user_id": fanvue_user_id,

            "qualification_type": "FOLLOWER_WELCOME",

            "offer_style": "LIGHT_TEASE",
            "goal": "EARLY_SPENDER_DETECTION",

            "qualification_event": qualification_event,

            "safe_for_new_follower": True,
            "aggressive_sales_disabled": True,
        }