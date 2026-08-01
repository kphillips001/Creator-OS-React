DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.sales_sessions
        WHERE commercial_foundation_type <> 'PHOTOSHOOT'
    ) THEN
        RAISE EXCEPTION
            'Cannot roll back Sales Session foundations while non-Photoshoot Sessions exist.';
    END IF;
END $$;

ALTER TABLE public.sales_sessions
    DROP CONSTRAINT IF EXISTS sales_sessions_commercial_foundation_shape_check;

ALTER TABLE public.sales_sessions
    DROP CONSTRAINT IF EXISTS sales_sessions_commercial_foundation_type_check;

ALTER TABLE public.sales_sessions
    ALTER COLUMN commercial_foundation_reference SET NOT NULL;

ALTER TABLE public.sales_sessions
    ADD CONSTRAINT sales_sessions_commercial_foundation_type_check
    CHECK (commercial_foundation_type IN ('PHOTOSHOOT'));

ALTER TABLE public.sales_sessions
    ADD CONSTRAINT sales_sessions_commercial_foundation_reference_check
    CHECK (BTRIM(commercial_foundation_reference) <> '');
