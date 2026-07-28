ALTER TABLE public.ava_coaching_recommendations
    DROP CONSTRAINT IF EXISTS ava_coaching_recommendations_status_check;
UPDATE public.ava_coaching_recommendations
SET status='APPROVED',updated_at=NOW()
WHERE status='APPROVED_FOR_VERSION';
ALTER TABLE public.ava_coaching_recommendations
    ADD CONSTRAINT ava_coaching_recommendations_status_check
    CHECK (status IN ('PENDING','APPROVED','REJECTED','DISMISSED','APPLIED'));

ALTER TABLE public.ava_applied_improvements
    DROP CONSTRAINT IF EXISTS ava_applied_improvements_status_check;
UPDATE public.ava_applied_improvements SET status='APPLIED'
WHERE status='APPROVED_FOR_VERSION';
ALTER TABLE public.ava_applied_improvements ALTER COLUMN status SET DEFAULT 'APPLIED';
ALTER TABLE public.ava_applied_improvements
    ADD CONSTRAINT ava_applied_improvements_status_check CHECK(status='APPLIED');

ALTER TABLE public.ava_personality_versions
    DROP CONSTRAINT IF EXISTS ava_personality_versions_status_check;
UPDATE public.ava_personality_versions SET status='TARGET' WHERE status='DRAFT';
ALTER TABLE public.ava_personality_versions
    ADD CONSTRAINT ava_personality_versions_status_check
    CHECK (status IN ('BASELINE','TARGET','RETIRED'));
