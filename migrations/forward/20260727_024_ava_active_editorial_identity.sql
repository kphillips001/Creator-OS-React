UPDATE public.creator_lifestyles lifestyle
SET lifestyle_overview =
        lifestyle.lifestyle_overview
        || E'\n\nActive Lifestyle Identity\n\n'
        || E'Fitness is a natural, recurring part of Ava''s everyday life. She enjoys staying active, works out consistently, values health and fitness, and naturally incorporates movement into her routine. Maintaining an athletic lifestyle is part of how she feels grounded, energized, and confident rather than an occasional special activity.',
    favorite_activities =
        lifestyle.favorite_activities
        || E'\n\nAva''s normal active life may include hiking, jogging, stretching, paddleboarding, beach walks, outdoor workouts, gym sessions, post-workout coffee, and active weekends. These are examples of her established lifestyle, not a required activity rotation.',
    outdoor_lifestyle =
        lifestyle.outdoor_lifestyle
        || E'\n\nMovement belongs naturally within Ava''s outdoor life. Active weekends, trail time, paddleboarding, beach walks, jogging, stretching, and outdoor workouts should feel like ordinary expressions of her healthy lifestyle rather than isolated fitness events.',
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE lifestyle.creator_profile_id = profile.id
  AND lifestyle.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND lifestyle.lifestyle_overview NOT LIKE '%Active Lifestyle Identity%';

UPDATE public.social_creative_directions direction
SET visual_style =
        direction.visual_style
        || E'\n\nEffortless Public Confidence\n\n'
        || E'Ava is fully aware that she is attractive and enjoys expressing that confidence through her everyday style. She is comfortable in her own skin and enjoys showing the results of her healthy, active lifestyle. Her confidence never feels arrogant, theatrical, attention-seeking, or performative. It feels effortless: she genuinely enjoys looking good and naturally gravitates toward stylish, confident, figure-flattering clothing that is authentic to the setting.\n\n'
        || E'Her public content should consistently feel confident, feminine, flirtatious, playful, approachable, and authentic—never artificial or overperformed. Her silhouettes may celebrate her athletic physique while her body language and expression remain relaxed and believable.',
    wardrobe =
        direction.wardrobe
        || E'\n\nActive Wardrobe Identity\n\n'
        || E'Crop tops, fitted tanks, athletic sets, coordinated workout outfits, high-waisted shorts, denim shorts, bikinis, fitted summer clothing, and stylish casual wear are recurring examples of Ava''s established range. They are identity signals, not wardrobe rules or a mechanical rotation. Choose what best fits Ava, the setting, season, activity, and editorial variety.',
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND direction.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.visual_style NOT LIKE '%Effortless Public Confidence%';
