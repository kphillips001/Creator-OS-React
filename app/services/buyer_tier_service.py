class BuyerTierService:
    """
    STEP 11.11

    Determines buyer tier based on
    lifetime spending behavior.
    """

    def determine_buyer_tier(
        self,
        total_spend: float,
        purchase_count: int,
    ) -> str:

        #
        # WHALE
        #

        if total_spend >= 1000:
            return "WHALE"

        #
        # HIGH VALUE
        #

        elif total_spend >= 300:
            return "HIGH_VALUE"

        #
        # ACTIVE BUYER
        #

        elif total_spend >= 100:
            return "ACTIVE_BUYER"

        #
        # LOW SPENDER
        #

        elif total_spend > 0:
            return "LOW_SPENDER"

        #
        # NON BUYER
        #

        return "NON_BUYER"