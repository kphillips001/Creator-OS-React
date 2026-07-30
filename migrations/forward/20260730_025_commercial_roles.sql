CREATE TABLE IF NOT EXISTS public.commercial_role_assignments (
    assignment_id UUID PRIMARY KEY,
    asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    role TEXT NOT NULL CHECK (
        role IN (
            'DISCOVERY','HERO','CORE','PROGRESSION',
            'PREMIUM','FINALE','BONUS'
        )
    ),
    state TEXT NOT NULL CHECK (
        state IN ('SUGGESTED','APPROVED','REJECTED','INACTIVE','RETIRED')
    ),
    origin TEXT NOT NULL CHECK (
        origin IN ('AI_SUGGESTED','CREATOR_ASSIGNED','OPERATOR_ASSIGNED')
    ),
    rationale TEXT NULL,
    suggestion_confidence DOUBLE PRECISION NULL CHECK (
        suggestion_confidence IS NULL
        OR suggestion_confidence BETWEEN 0.0 AND 1.0
    ),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    assigned_by_type TEXT NULL CHECK (
        assigned_by_type IS NULL
        OR assigned_by_type IN ('AI','CREATOR','OPERATOR')
    ),
    assigned_by_identifier TEXT NULL,
    vocabulary_version TEXT NOT NULL DEFAULT '1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_id, role)
);

CREATE INDEX IF NOT EXISTS idx_commercial_roles_creator_state
    ON public.commercial_role_assignments (
        creator_profile_id, state, updated_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_commercial_roles_asset
    ON public.commercial_role_assignments (asset_id, role);

CREATE TABLE IF NOT EXISTS public.commercial_role_history (
    history_id BIGSERIAL PRIMARY KEY,
    assignment_id UUID NOT NULL
        REFERENCES public.commercial_role_assignments(assignment_id)
        ON DELETE RESTRICT,
    asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    role TEXT NOT NULL CHECK (
        role IN (
            'DISCOVERY','HERO','CORE','PROGRESSION',
            'PREMIUM','FINALE','BONUS'
        )
    ),
    event_type TEXT NOT NULL,
    previous_state TEXT NULL CHECK (
        previous_state IS NULL
        OR previous_state IN (
            'SUGGESTED','APPROVED','REJECTED','INACTIVE','RETIRED'
        )
    ),
    new_state TEXT NOT NULL CHECK (
        new_state IN (
            'SUGGESTED','APPROVED','REJECTED','INACTIVE','RETIRED'
        )
    ),
    actor_type TEXT NOT NULL CHECK (
        actor_type IN ('AI','CREATOR','OPERATOR')
    ),
    actor_identifier TEXT NULL,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commercial_role_history_assignment
    ON public.commercial_role_history (assignment_id, created_at, history_id);

CREATE INDEX IF NOT EXISTS idx_commercial_role_history_asset
    ON public.commercial_role_history (
        creator_profile_id, asset_id, created_at DESC
    );

