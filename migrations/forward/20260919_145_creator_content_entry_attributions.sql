BEGIN;

CREATE TABLE public.creator_content_entry_attributions (
    attribution_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    publication_id UUID NOT NULL REFERENCES public.creator_content_publications(publication_id) ON DELETE RESTRICT,
    token_digest CHAR(64) NOT NULL UNIQUE,
    source_platform TEXT NOT NULL CHECK (source_platform = 'telegram'),
    provenance_method TEXT NOT NULL CHECK (provenance_method = 'TELEGRAM_DIRECT_CHAT_DRAFT'),
    status TEXT NOT NULL CHECK (status IN ('TOKEN_CREATED','CTA_ATTACHED','CTA_ATTACHMENT_FAILED','REVOKED')),
    token_created_at TIMESTAMPTZ NOT NULL,
    cta_attached_at TIMESTAMPTZ NULL,
    last_error_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT creator_content_entry_attribution_publication_unique UNIQUE (publication_id)
);

CREATE TABLE public.creator_content_entry_events (
    entry_event_id UUID PRIMARY KEY,
    attribution_id UUID NOT NULL REFERENCES public.creator_content_entry_attributions(attribution_id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL,
    publication_id UUID NOT NULL REFERENCES public.creator_content_publications(publication_id) ON DELETE RESTRICT,
    event_status TEXT NOT NULL CHECK (event_status = 'ENTRY_OBSERVED'),
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    inbound_telegram_message_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT creator_content_entry_event_identity_unique
      UNIQUE (attribution_id, telegram_user_id, telegram_chat_id, inbound_telegram_message_id)
);

CREATE INDEX idx_creator_content_entry_attribution_creator
    ON public.creator_content_entry_attributions (creator_profile_id, created_at DESC);
CREATE INDEX idx_creator_content_entry_attribution_publication
    ON public.creator_content_entry_attributions (publication_id);
CREATE INDEX idx_creator_content_entry_event_customer
    ON public.creator_content_entry_events
    (creator_profile_id, telegram_user_id, observed_at DESC);
CREATE INDEX idx_creator_content_entry_event_publication
    ON public.creator_content_entry_events (publication_id, observed_at DESC);

COMMIT;
