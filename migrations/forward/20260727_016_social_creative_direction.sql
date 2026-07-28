CREATE TABLE IF NOT EXISTS public.social_creative_directions (
    id BIGSERIAL PRIMARY KEY,
    creator_profile_id INTEGER NOT NULL UNIQUE
        REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
    fanvue_account_id TEXT NOT NULL UNIQUE,
    purpose TEXT NOT NULL,
    wardrobe TEXT NOT NULL,
    visual_style TEXT NOT NULL,
    seasonal_guidance TEXT NOT NULL,
    things_to_avoid TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.social_creative_directions IS
    'Account-scoped editable social creative direction. Not consumed by generation.';

INSERT INTO public.social_creative_directions (
    creator_profile_id,
    fanvue_account_id,
    purpose,
    wardrobe,
    visual_style,
    seasonal_guidance,
    things_to_avoid
)
SELECT
    profile.id,
    profile.fanvue_account_id,
    'Create visually engaging content for public social platforms that attracts attention, encourages conversation, and naturally guides followers toward premium experiences.',
    E'Ava should generally wear flattering, form-fitting clothing that highlights her figure while remaining believable for everyday life.\n\nPreferred wardrobe may include:\n\n- leggings\n- yoga pants\n- crop tops\n- tank tops\n- fitted jeans\n- athletic shorts\n- swimsuits\n- fitted dresses\n- casual athletic wear',
    E'Images should generally portray Ava as naturally beautiful, confident, approachable, playful, and feminine.\n\nSocial content may emphasize:\n\n- cleavage\n- midriff\n- curves\n- toned legs\n- confident posture\n\nwhile maintaining an authentic girl-next-door lifestyle feel.',
    E'Creator_OS should automatically adapt clothing, scenery, and activities to the current season.\n\nAvoid obviously out-of-season clothing or environments unless specifically requested.\n\nMaintain believable seasonal consistency.',
    E'Avoid:\n\n- repetitive outfits\n- unrealistic fashion-editorial posing\n- plastic-looking skin\n- awkward posing\n- overly artificial glamour\n- clothing that hides Ava''s figure without creative purpose'
FROM public.creator_profiles profile
ON CONFLICT (creator_profile_id) DO NOTHING;
