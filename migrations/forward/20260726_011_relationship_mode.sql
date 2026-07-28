ALTER TABLE public.commerce_recommendation_outcomes
    DROP CONSTRAINT IF EXISTS commerce_recommendation_outcomes_outcome_type_check;
ALTER TABLE public.commerce_recommendation_outcomes
    ADD CONSTRAINT commerce_recommendation_outcomes_outcome_type_check
    CHECK (outcome_type IN (
        'PRESENTED','OPENED','PURCHASED','IGNORED','EXPIRED',
        'DECLINED','ABANDONED','REFUNDED','WOULD_HAVE_SOLD'
    ));

ALTER TABLE public.customer_commerce_profiles
    DROP CONSTRAINT IF EXISTS customer_commerce_profile_state_check;
ALTER TABLE public.customer_commerce_profiles
    ADD CONSTRAINT customer_commerce_profile_state_check CHECK (
        profile_state IN (
            'UNKNOWN','PROSPECT','LEAD','FIRST_PURCHASE','REPEAT_BUYER',
            'VIP','HIGH_VALUE','INACTIVE','PRE_LAUNCH_INTEREST'
        )
    );
