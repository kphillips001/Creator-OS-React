-- A Photoshoot cover is its first ordered member (the Photoshoot Seed Image),
-- never the separate canonical identity reference used during generation.
WITH first_members AS (
    SELECT DISTINCT ON (photoshoot_session_id)
        photoshoot_session_id,
        asset_id
    FROM public.photoshoot_asset_memberships
    WHERE approved = TRUE
    ORDER BY photoshoot_session_id, shot_order
)
UPDATE public.photoshoot_commerce_deliverables AS deliverable
SET hero_asset_id = first_members.asset_id,
    updated_at = now()
FROM first_members
WHERE first_members.photoshoot_session_id = deliverable.photoshoot_session_id
  AND deliverable.hero_asset_id IS DISTINCT FROM first_members.asset_id;
