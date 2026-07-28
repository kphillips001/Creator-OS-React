CREATE TABLE IF NOT EXISTS public.creator_lifestyles (
    id BIGSERIAL PRIMARY KEY,
    creator_profile_id INTEGER NOT NULL UNIQUE
        REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
    fanvue_account_id TEXT NOT NULL UNIQUE,
    career TEXT NOT NULL,
    lifestyle_overview TEXT NOT NULL,
    favorite_activities TEXT NOT NULL,
    weekend_escapes TEXT NOT NULL,
    small_town_roots TEXT NOT NULL,
    outdoor_lifestyle TEXT NOT NULL,
    personal_style TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.creator_lifestyles IS
    'Account-scoped editable creator lifestyle. Not consumed by generation.';

INSERT INTO public.creator_lifestyles (
    creator_profile_id,
    fanvue_account_id,
    career,
    lifestyle_overview,
    favorite_activities,
    weekend_escapes,
    small_town_roots,
    outdoor_lifestyle,
    personal_style
)
SELECT
    profile.id,
    profile.fanvue_account_id,
    'Ava works as a marketing and events professional. Her work keeps her connected to local destinations, hospitality, tourism, community events, and new experiences.',
    'Ava balances modern city life with the places and experiences that make her feel grounded. She loves both the coast and the mountains and naturally makes room for outdoor life, spontaneous plans, and slower everyday moments.',
    E'Ava enjoys:\n\n- hiking\n- spending time at lakes\n- camping\n- beach days\n- road trips\n- coffee shops\n- bookstores\n- festivals\n- exploring new places\n- spending time outdoors',
    'Weekend escapes often take Ava toward the coast or the mountains. She enjoys cabins, lakes, camping trips, beach weekends, scenic road trips, and discovering small towns or local places along the way.',
    'Ava grew up with small-town roots and still values community, genuine relationships, familiar places, and a slower pace of life. Those roots keep her approachable and grounded even as she explores new places and opportunities.',
    'Outdoor life is a natural part of Ava''s routine. She enjoys hiking, lakes, cabins, camping, beaches, mountain air, scenic drives, and simply spending time outside whenever she can.',
    'Ava''s natural clothing style is feminine, fitted, flattering, stylish, and confident. She prefers clothes that feel comfortable and believable for what she is doing while still expressing her personal sense of style.'
FROM public.creator_profiles profile
ON CONFLICT (creator_profile_id) DO NOTHING;
