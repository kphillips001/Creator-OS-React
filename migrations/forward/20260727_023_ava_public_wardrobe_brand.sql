UPDATE public.social_creative_directions direction
SET wardrobe =
        direction.wardrobe
        || E'\n\nAva Public Wardrobe Brand\n\n'
        || E'Ava''s public X brand should naturally favor confident feminine styling, figure-flattering silhouettes, and visually compelling outfits rather than drifting toward uniformly conservative commercial fashion.\n\n'
        || E'Midriff-visible styling is a normal, recurring part of Ava''s public brand when it suits the season, environment, and activity. It should not appear in every image. Across a collection, use editorial judgment to maintain natural variety in what each look emphasizes, including silhouette, neckline, legs, layering, swimwear, dresses, athletic styling, and fitted casual styling.\n\n'
        || E'Crop tops, fitted tanks, coordinated or athletic sets, denim shorts, short figure-flattering casual looks, bikinis, and stylish scene-appropriate dresses are useful examples of Ava''s established range, not a required rotation or wardrobe template. Infer the strongest styling from Social Creative Direction, Creative Intelligence, season, setting, activity, and the rest of the current batch.\n\n'
        || E'Autonomous Inspiration swimwear guidance: when an autonomously selected scene naturally calls for swimwear, choose a bikini. One-piece swimsuits and other one-piece swim silhouettes remain available only when the operator explicitly requests them through the manual Creative Studio workflow. Never override explicit manual wardrobe intent.',
    updated_at = NOW()
FROM public.creator_profiles profile
WHERE direction.creator_profile_id = profile.id
  AND direction.fanvue_account_id = profile.fanvue_account_id
  AND profile.persona_name = 'Ava Blackthorne'
  AND direction.wardrobe NOT LIKE '%Ava Public Wardrobe Brand%';
