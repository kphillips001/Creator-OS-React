CREATE INDEX IF NOT EXISTS idx_commercial_roles_asset
    ON public.commercial_role_assignments (asset_id, role);
