BEGIN;

CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY,
    creator_profile_id INTEGER NULL
        REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    legacy_content_item_id INTEGER NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    sku TEXT NOT NULL,
    product_type TEXT NOT NULL CHECK (
        product_type IN (
            'SINGLE_IMAGE',
            'SINGLE_VIDEO',
            'PHOTO_SET',
            'VIDEO_SET',
            'SESSION',
            'STORY',
            'BUNDLE',
            'CUSTOM'
        )
    ),
    title TEXT NOT NULL,
    description TEXT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'active', 'retired', 'archived')
    ),
    base_price_minor BIGINT NULL CHECK (
        base_price_minor IS NULL OR base_price_minor >= 0
    ),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    access_type TEXT NOT NULL DEFAULT 'permanent' CHECK (
        access_type IN (
            'permanent',
            'time_limited',
            'subscription',
            'fulfillment'
        )
    ),
    access_duration_seconds BIGINT NULL,
    supersedes_product_id UUID NULL
        REFERENCES public.products(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at TIMESTAMPTZ NULL,
    retired_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT products_sku_key UNIQUE (sku),
    CONSTRAINT products_legacy_content_item_key
        UNIQUE (legacy_content_item_id),
    CONSTRAINT products_access_duration_check CHECK (
        access_type <> 'time_limited'
        OR access_duration_seconds > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_products_status
    ON public.products(status);
CREATE INDEX IF NOT EXISTS idx_products_product_type
    ON public.products(product_type);
CREATE INDEX IF NOT EXISTS idx_products_creator_profile
    ON public.products(creator_profile_id);

CREATE TABLE IF NOT EXISTS public.product_assets (
    product_id UUID NOT NULL
        REFERENCES public.products(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
    role TEXT NOT NULL DEFAULT 'primary' CHECK (
        role IN (
            'primary',
            'preview',
            'cover',
            'chapter',
            'bonus',
            'attachment',
            'fulfillment'
        )
    ),
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    delivery_mode TEXT NOT NULL DEFAULT 'protected' CHECK (
        delivery_mode IN (
            'preview',
            'protected',
            'download',
            'stream',
            'manual'
        )
    ),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (product_id, asset_id, role),
    CONSTRAINT product_assets_product_position_key
        UNIQUE (product_id, position)
);

CREATE INDEX IF NOT EXISTS idx_product_assets_asset_id
    ON public.product_assets(asset_id);

CREATE TABLE IF NOT EXISTS public.customer_entitlements (
    id UUID PRIMARY KEY,
    core_user_id UUID NULL,
    legacy_fanvue_account_id BIGINT NULL,
    legacy_fanvue_user_id TEXT NULL,
    product_id UUID NOT NULL
        REFERENCES public.products(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN (
            'pending',
            'active',
            'fulfilled',
            'expired',
            'revoked',
            'refunded',
            'cancelled'
        )
    ),
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'purchase',
            'ppv_unlock',
            'subscription',
            'promotion',
            'manual_grant',
            'custom_fulfillment'
        )
    ),
    commerce_provider TEXT NULL,
    provider_transaction_id TEXT NULL,
    provider_event_id TEXT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NULL,
    fulfilled_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    revocation_reason TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT customer_entitlements_identity_check CHECK (
        core_user_id IS NOT NULL
        OR (
            legacy_fanvue_account_id IS NOT NULL
            AND legacy_fanvue_user_id IS NOT NULL
            AND BTRIM(legacy_fanvue_user_id) <> ''
        )
    ),
    CONSTRAINT customer_entitlements_expiry_check CHECK (
        expires_at IS NULL OR expires_at > valid_from
    )
);

CREATE INDEX IF NOT EXISTS idx_customer_entitlements_core_user
    ON public.customer_entitlements(core_user_id, status);
CREATE INDEX IF NOT EXISTS idx_customer_entitlements_legacy_user
    ON public.customer_entitlements(
        legacy_fanvue_account_id,
        legacy_fanvue_user_id,
        status
    );
CREATE INDEX IF NOT EXISTS idx_customer_entitlements_product
    ON public.customer_entitlements(product_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_entitlements_provider_transaction_product
    ON public.customer_entitlements(
        commerce_provider,
        provider_transaction_id,
        product_id
    )
    WHERE commerce_provider IS NOT NULL
      AND provider_transaction_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_entitlements_provider_event_product
    ON public.customer_entitlements(
        commerce_provider,
        provider_event_id,
        product_id
    )
    WHERE commerce_provider IS NOT NULL
      AND provider_event_id IS NOT NULL;

COMMIT;
