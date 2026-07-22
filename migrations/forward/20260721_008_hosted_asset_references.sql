CREATE TABLE IF NOT EXISTS public.hosted_asset_references (
    reference_id TEXT PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
    host_name TEXT NOT NULL,
    hosted_url TEXT NOT NULL,
    source_checksum TEXT NOT NULL,
    source_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at TIMESTAMPTZ NULL,
    last_used_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    is_current BOOLEAN NOT NULL DEFAULT false,
    last_error_code TEXT NULL,
    last_error_message TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT hosted_asset_reference_status_check CHECK (status IN ('PENDING','READY','STALE','FAILED')),
    CONSTRAINT hosted_asset_reference_https_check CHECK (hosted_url ~ '^https://'),
    CONSTRAINT hosted_asset_reference_asset_checksum_unique UNIQUE (asset_id,host_name,source_checksum)
);

CREATE UNIQUE INDEX IF NOT EXISTS hosted_asset_reference_current_idx
    ON public.hosted_asset_references(asset_id,host_name) WHERE is_current=TRUE;

CREATE INDEX IF NOT EXISTS hosted_asset_reference_lookup_idx
    ON public.hosted_asset_references(asset_id,host_name,source_checksum,status);
