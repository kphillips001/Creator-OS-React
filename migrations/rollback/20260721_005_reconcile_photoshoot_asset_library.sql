UPDATE public.photoshoot_commerce_deliverables
SET registration_state='REGISTERED', updated_at=now()
WHERE registration_state='IN_ASSET_LIBRARY'
  AND is_archived=FALSE;
