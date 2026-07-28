UPDATE public.customer_commerce_profiles
SET profile_state='LEAD'
WHERE profile_state='PRE_LAUNCH_INTEREST';
DELETE FROM public.commerce_recommendation_outcomes
WHERE outcome_type='WOULD_HAVE_SOLD';

ALTER TABLE public.commerce_recommendation_outcomes
    DROP CONSTRAINT IF EXISTS commerce_recommendation_outcomes_outcome_type_check;
ALTER TABLE public.commerce_recommendation_outcomes
    ADD CONSTRAINT commerce_recommendation_outcomes_outcome_type_check
    CHECK (outcome_type IN (
        'PRESENTED','OPENED','PURCHASED','IGNORED','EXPIRED',
        'DECLINED','ABANDONED','REFUNDED'
    ));

ALTER TABLE public.customer_commerce_profiles
    DROP CONSTRAINT IF EXISTS customer_commerce_profile_state_check;
ALTER TABLE public.customer_commerce_profiles
    ADD CONSTRAINT customer_commerce_profile_state_check CHECK (
        profile_state IN (
            'UNKNOWN','PROSPECT','LEAD','FIRST_PURCHASE','REPEAT_BUYER',
            'VIP','HIGH_VALUE','INACTIVE'
        )
    );
