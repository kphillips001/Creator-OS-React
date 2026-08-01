ALTER TABLE public.sales_sessions
    DROP CONSTRAINT IF EXISTS sales_sessions_commercial_foundation_type_check;

ALTER TABLE public.sales_sessions
    DROP CONSTRAINT IF EXISTS sales_sessions_commercial_foundation_reference_check;

ALTER TABLE public.sales_sessions
    ALTER COLUMN commercial_foundation_reference DROP NOT NULL;

ALTER TABLE public.sales_sessions
    ADD CONSTRAINT sales_sessions_commercial_foundation_type_check
    CHECK (commercial_foundation_type IN ('PHOTOSHOOT', 'CONVERSATION'));

ALTER TABLE public.sales_sessions
    ADD CONSTRAINT sales_sessions_commercial_foundation_shape_check
    CHECK (
        (
            commercial_foundation_type = 'PHOTOSHOOT'
            AND commercial_foundation_reference IS NOT NULL
            AND BTRIM(commercial_foundation_reference) <> ''
        )
        OR
        (
            commercial_foundation_type = 'CONVERSATION'
            AND commercial_foundation_reference IS NULL
            AND conversation_thread_id IS NOT NULL
        )
    );
