UPDATE public.social_creative_directions direction
SET visual_style = split_part(
        direction.visual_style,
        E'\n\nFacial Expression and Emotional Presentation\n\n',
        1
    ),
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND direction.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.visual_style LIKE
      '%Facial Expression and Emotional Presentation%';
