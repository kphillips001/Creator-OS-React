class FanvueVaultAssignmentService:
    """
    Fanvue publishing-target routing.

    Determines:
    - destination (vault routing)
    - vault folder name
    - delivery method (post_now vs scheduled)
    """

    def assign_destination(
        self,
        upload_intent: str,
        delivery_method: str = None,  # "post_now" | "scheduled"
    ) -> dict:

        # ------------------------------------------
        # WALL CONTENT (special case)
        # ------------------------------------------
        if upload_intent in ["wall_image", "wall_video"]:
            return {
                "destination": "wall",
                "vault_folder": "Wall",
                "delivery_method": delivery_method or "post_now",
            }

        # ------------------------------------------
        # TEASER
        # ------------------------------------------
        if upload_intent in ["teaser_image", "teaser_video"]:
            return {
                "destination": "teaser",
                "vault_folder": "Teasers",
                "delivery_method": "chat",
            }

        # ------------------------------------------
        # VIP
        # ------------------------------------------
        if upload_intent in ["vip_image", "vip_video"]:
            return {
                "destination": "vip",
                "vault_folder": "VIP",
                "delivery_method": "chat",
            }

        # ------------------------------------------
        # PREMIUM
        # ------------------------------------------
        if upload_intent in ["premium_image", "premium_video"]:
            return {
                "destination": "premium",
                "vault_folder": "Premium",
                "delivery_method": "chat",
            }

        # ------------------------------------------
        # FALLBACK
        # ------------------------------------------
        return {
            "destination": "unknown",
            "vault_folder": None,
            "delivery_method": "unknown",
        }
