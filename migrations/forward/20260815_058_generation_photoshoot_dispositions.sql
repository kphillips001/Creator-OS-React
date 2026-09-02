BEGIN;

ALTER TABLE public.generation_image_dispositions
  DROP CONSTRAINT IF EXISTS generation_image_dispositions_owner_id_fkey;

ALTER TABLE public.generation_image_dispositions
  DROP CONSTRAINT IF EXISTS generation_image_dispositions_owner_check;

ALTER TABLE public.generation_image_dispositions
  ADD CONSTRAINT generation_image_dispositions_owner_check
  CHECK (owner IN ('BUNDLE_STUDIO','PHOTOSHOOT'));

ALTER TABLE public.generation_image_dispositions
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

INSERT INTO public.generation_image_dispositions(image_id,owner,owner_id)
SELECT member.image_id,'PHOTOSHOOT',member.intake_id
FROM public.assembled_photoshoot_intake_members member
JOIN public.assembled_photoshoot_intakes intake USING(intake_id)
JOIN public.photoshoot_commerce_deliverables deliverable
  ON deliverable.source_kind='GENERATION_LIBRARY_IMPORT'
 AND deliverable.source_reference=intake.intake_id
JOIN public.photoshoot_asset_memberships membership
  ON membership.photoshoot_session_id=deliverable.photoshoot_session_id
 AND membership.asset_id=member.asset_id
 AND membership.approved=TRUE
WHERE intake.status='SUCCEEDED'
ON CONFLICT(image_id) DO NOTHING;

COMMIT;
