UPDATE public.social_creative_directions direction
SET wardrobe = split_part(
        direction.wardrobe,
        E'\n\nAva Public Wardrobe Brand\n\n',
        1
    ),
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND direction.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.wardrobe LIKE '%Ava Public Wardrobe Brand%';
