BEGIN;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS fulfillment_strategy TEXT;

UPDATE public.products
SET fulfillment_strategy = CASE product_type
    WHEN 'SINGLE_IMAGE' THEN 'FANVUE_PAID_CHAT'
    WHEN 'SINGLE_VIDEO' THEN 'FANVUE_PAID_CHAT'
    WHEN 'PHOTO_SET' THEN 'FANVUE_PAID_CHAT'
    WHEN 'VIDEO_SET' THEN 'FANVUE_PAID_CHAT'
    WHEN 'STORY' THEN 'FANVUE_PAID_POST'
    WHEN 'SESSION' THEN 'FANVUE_PAID_CHAT'
    WHEN 'BUNDLE' THEN 'MANUAL_FUTURE'
    ELSE 'MANUAL_FUTURE'
END
WHERE fulfillment_strategy IS NULL
   OR fulfillment_strategy = '';

ALTER TABLE public.products
    ALTER COLUMN fulfillment_strategy SET DEFAULT 'MANUAL_FUTURE',
    ALTER COLUMN fulfillment_strategy SET NOT NULL;

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_fulfillment_strategy_check,
    ADD CONSTRAINT products_fulfillment_strategy_check CHECK (
        fulfillment_strategy IN (
            'FANVUE_PAID_CHAT',
            'FANVUE_PAID_POST',
            'MEDIA_LINK_FUTURE',
            'MANUAL_FUTURE'
        )
    );

CREATE INDEX IF NOT EXISTS idx_products_fulfillment_strategy
    ON public.products(fulfillment_strategy);

COMMIT;
