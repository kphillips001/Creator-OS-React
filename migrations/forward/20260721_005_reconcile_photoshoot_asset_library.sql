-- Rows promoted by the superseded direct-to-Commerce workflow must pass through
-- the Asset Library under the unified curation model.
UPDATE public.photoshoot_commerce_deliverables
SET registration_state='IN_ASSET_LIBRARY', updated_at=now()
WHERE registration_state='REGISTERED'
  AND is_archived=FALSE;
