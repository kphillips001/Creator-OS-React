CREATE TABLE IF NOT EXISTS public.sales_sessions (
    sales_session_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL
        REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    telegram_identity_mapping_id BIGINT NULL
        REFERENCES public.telegram_identity_map(id) ON DELETE SET NULL,
    conversation_thread_id BIGINT NULL
        REFERENCES public.chat_threads(id) ON DELETE SET NULL,
    commercial_foundation_type TEXT NOT NULL CHECK (
        commercial_foundation_type IN ('PHOTOSHOOT')
    ),
    commercial_foundation_reference TEXT NOT NULL CHECK (
        BTRIM(commercial_foundation_reference) <> ''
    ),
    state TEXT NOT NULL CHECK (
        state IN (
            'ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING',
            'COMPLETED','EXPIRED','ABANDONED','CANCELLED'
        )
    ),
    progression_stage TEXT NOT NULL CHECK (
        progression_stage IN (
            'DISCOVERY','CORE','PROGRESSION','PREMIUM','FINALE','BONUS'
        )
    ),
    objective TEXT NULL,
    commercial_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome TEXT NULL CHECK (
        outcome IS NULL OR outcome IN (
            'COMPLETED_WITH_PURCHASE','COMPLETED_WITHOUT_PURCHASE',
            'EXPIRED','ABANDONED','CANCELLED'
        )
    ),
    terminal_reason TEXT NULL,
    started_by_type TEXT NOT NULL CHECK (
        started_by_type IN ('AI','CREATOR','OPERATOR')
    ),
    started_by_identifier TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_sessions_active_customer
    ON public.sales_sessions (
        creator_profile_id, fanvue_account_id, fanvue_user_id
    )
    WHERE state IN (
        'ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING'
    );

CREATE INDEX IF NOT EXISTS idx_sales_sessions_creator_activity
    ON public.sales_sessions (
        creator_profile_id, last_activity_at DESC, sales_session_id
    );

CREATE INDEX IF NOT EXISTS idx_sales_sessions_foundation
    ON public.sales_sessions (
        creator_profile_id, commercial_foundation_type,
        commercial_foundation_reference
    );

CREATE TABLE IF NOT EXISTS public.sales_session_purchase_intents (
    sales_session_id UUID NOT NULL
        REFERENCES public.sales_sessions(sales_session_id)
        ON DELETE RESTRICT,
    purchase_intent_id UUID NOT NULL
        REFERENCES public.purchase_intents(purchase_intent_id)
        ON DELETE RESTRICT,
    sequence_index INTEGER NOT NULL CHECK (sequence_index > 0),
    associated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sales_session_id, purchase_intent_id),
    UNIQUE (purchase_intent_id),
    UNIQUE (sales_session_id, sequence_index)
);

CREATE TABLE IF NOT EXISTS public.sales_session_history (
    history_id BIGSERIAL PRIMARY KEY,
    sales_session_id UUID NOT NULL
        REFERENCES public.sales_sessions(sales_session_id)
        ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    previous_state TEXT NULL CHECK (
        previous_state IS NULL OR previous_state IN (
            'ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING',
            'COMPLETED','EXPIRED','ABANDONED','CANCELLED'
        )
    ),
    new_state TEXT NOT NULL CHECK (
        new_state IN (
            'ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING',
            'COMPLETED','EXPIRED','ABANDONED','CANCELLED'
        )
    ),
    previous_progression_stage TEXT NULL CHECK (
        previous_progression_stage IS NULL OR previous_progression_stage IN (
            'DISCOVERY','CORE','PROGRESSION','PREMIUM','FINALE','BONUS'
        )
    ),
    new_progression_stage TEXT NOT NULL CHECK (
        new_progression_stage IN (
            'DISCOVERY','CORE','PROGRESSION','PREMIUM','FINALE','BONUS'
        )
    ),
    purchase_intent_id UUID NULL
        REFERENCES public.purchase_intents(purchase_intent_id)
        ON DELETE RESTRICT,
    actor_type TEXT NOT NULL CHECK (
        actor_type IN ('AI','CREATOR','OPERATOR','SYSTEM')
    ),
    actor_identifier TEXT NULL,
    reason TEXT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sales_session_history_session
    ON public.sales_session_history (
        sales_session_id, occurred_at, history_id
    );
