UPDATE public.social_creative_directions direction
SET wardrobe =
        direction.wardrobe
        || E'\n\nBrand Styling and Silhouette Direction\n\n'
        || E'Ava''s established public brand favors confident, feminine, stylish, figure-flattering fashion that remains believable and appropriate to the current season, setting, activity, and mood.\n\n'
        || E'Styling should be inferred editorially for each scene rather than selected from a fixed wardrobe formula. Across a collection, consider variety in silhouette, neckline, garment structure, layering, and coverage so the images do not feel like repeated versions of the same outfit.\n\n'
        || E'Editorial variety must remain natural. Do not force exposure, assign coverage targets, rotate through a wardrobe template, or make styling less authentic merely to create difference. Social Creative Direction, Creative Intelligence, season, and setting should guide the final choice.',
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND direction.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.wardrobe NOT LIKE
      '%Brand Styling and Silhouette Direction%';
