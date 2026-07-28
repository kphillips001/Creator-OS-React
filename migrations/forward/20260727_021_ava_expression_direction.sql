UPDATE public.social_creative_directions direction
SET visual_style =
        direction.visual_style
        || E'\n\nFacial Expression and Emotional Presentation\n\n'
        || E'Ava should generally favor understated, naturally expressive facial presentation suitable for her established X brand.\n\n'
        || E'Preferred expressions include:\n\n'
        || E'- soft smile\n'
        || E'- subtle smile\n'
        || E'- quiet confidence\n'
        || E'- playful smirk\n'
        || E'- relaxed warmth\n'
        || E'- gentle amusement\n'
        || E'- confident eye contact\n'
        || E'- natural candid expressions\n\n'
        || E'The overall emotional tone should feel feminine, confident, approachable, and effortlessly attractive rather than overly excited, exaggeratedly happy, highly animated, or theatrical.\n\n'
        || E'This is a preference, not a neutral-expression rule. Preserve natural variation, and allow an occasional larger smile when the scene genuinely supports it. Shift the average expression toward subtle confidence, soft smiles, and relaxed facial expressions.',
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND direction.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.visual_style NOT LIKE
      '%Facial Expression and Emotional Presentation%';
