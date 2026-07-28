UPDATE public.creator_lifestyles lifestyle
SET lifestyle_overview = split_part(lifestyle.lifestyle_overview, E'\n\nActive Lifestyle Identity\n\n', 1),
    favorite_activities = split_part(lifestyle.favorite_activities, E'\n\nAva''s normal active life may include', 1),
    outdoor_lifestyle = split_part(lifestyle.outdoor_lifestyle, E'\n\nMovement belongs naturally within Ava''s outdoor life.', 1),
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE lifestyle.creator_profile_id = profile.id
  AND profile.persona_name = 'Ava Blackthorne'
  AND lifestyle.lifestyle_overview LIKE '%Active Lifestyle Identity%';

UPDATE public.social_creative_directions direction
SET visual_style = split_part(direction.visual_style, E'\n\nEffortless Public Confidence\n\n', 1),
    wardrobe = split_part(direction.wardrobe, E'\n\nActive Wardrobe Identity\n\n', 1),
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.visual_style LIKE '%Effortless Public Confidence%';
