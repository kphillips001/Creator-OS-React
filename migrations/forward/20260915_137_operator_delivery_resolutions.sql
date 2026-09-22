BEGIN;

CREATE TABLE public.operator_delivery_resolutions (
    resolution_id UUID PRIMARY KEY,
    ordinary_operation_id UUID NOT NULL UNIQUE
        REFERENCES public.ordinary_chat_reply_operations(operation_id),
    creator_profile_id BIGINT NOT NULL CHECK (creator_profile_id > 0),
    fanvue_account_id BIGINT NOT NULL CHECK (fanvue_account_id > 0),
    relationship_key TEXT NOT NULL,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    purchase_intent_id UUID NULL REFERENCES public.purchase_intents(purchase_intent_id),
    outcome TEXT NOT NULL CHECK (outcome IN ('DELIVERED','NOT_DELIVERED')),
    provenance TEXT NOT NULL CHECK (provenance = 'OPERATOR_ATTESTED'),
    original_operation_state TEXT NOT NULL CHECK (original_operation_state = 'SEND_UNCERTAIN'),
    original_uncertainty_reason TEXT NOT NULL,
    presentation_mode TEXT NOT NULL,
    provider_acceptance_evidence BOOLEAN NOT NULL,
    provider_readback_evidence BOOLEAN NOT NULL,
    telegram_message_id BIGINT NULL,
    attested_presentation_at TIMESTAMPTZ NULL,
    resolved_by TEXT NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prior_purchase_intent_state TEXT NULL,
    corrected_purchase_intent_state TEXT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (outcome <> 'DELIVERED' OR attested_presentation_at IS NOT NULL),
    CHECK (telegram_message_id IS NULL OR telegram_message_id > 0)
);

CREATE INDEX operator_delivery_resolution_scope_idx
    ON public.operator_delivery_resolutions(
        creator_profile_id, fanvue_account_id, telegram_user_id, resolved_at DESC
    );
CREATE INDEX operator_delivery_resolution_purchase_intent_idx
    ON public.operator_delivery_resolutions(purchase_intent_id)
    WHERE purchase_intent_id IS NOT NULL;

ALTER TABLE public.conversation_resolution_plans
    DROP CONSTRAINT conversation_resolution_plans_action_type_check;
ALTER TABLE public.conversation_resolution_plans
    ADD CONSTRAINT conversation_resolution_plans_action_type_check CHECK (
        action_type IN ('ACKNOWLEDGE_ONLY','REQUEUE_CORRECTIVE_REPLY',
                        'RESOLVE_AS_SUPERSEDED','CONFIRM_DELIVERED',
                        'CONFIRM_NOT_DELIVERED')
    );

COMMIT;
