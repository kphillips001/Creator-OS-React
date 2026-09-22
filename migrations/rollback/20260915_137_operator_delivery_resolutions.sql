BEGIN;

ALTER TABLE public.conversation_resolution_plans
    DROP CONSTRAINT conversation_resolution_plans_action_type_check;
ALTER TABLE public.conversation_resolution_plans
    ADD CONSTRAINT conversation_resolution_plans_action_type_check CHECK (
        action_type IN ('ACKNOWLEDGE_ONLY','REQUEUE_CORRECTIVE_REPLY',
                        'RESOLVE_AS_SUPERSEDED')
    );
DROP TABLE IF EXISTS public.operator_delivery_resolutions;

COMMIT;
