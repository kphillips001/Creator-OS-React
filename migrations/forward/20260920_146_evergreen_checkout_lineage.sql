BEGIN;

-- References are canonical transaction IDs in the adapter's namespace, not a
-- second transaction store. No existing aliases or customer rows are modified.
CREATE TABLE public.evergreen_checkout_lineage (
    namespace TEXT NOT NULL CHECK (btrim(namespace) <> ''),
    alias_id UUID NOT NULL,
    original_transaction_id UUID NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    predecessor_id UUID NOT NULL,
    successor_id UUID NOT NULL,
    refresh_reason TEXT NOT NULL CHECK (refresh_reason = 'TRANSACTION_EXPIRED'),
    refreshed_at TIMESTAMPTZ NOT NULL,
    predecessor_price_minor BIGINT NOT NULL CHECK (predecessor_price_minor >= 0),
    successor_price_minor BIGINT NOT NULL CHECK (successor_price_minor >= 0),
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    eligibility_result TEXT NOT NULL CHECK (eligibility_result = 'ELIGIBLE'),
    runtime_state TEXT NOT NULL DEFAULT 'PENDING' CHECK (runtime_state IN ('PENDING','READY','FAILED')),
    runtime_reason TEXT NULL,
    PRIMARY KEY (namespace, original_transaction_id, generation),
    UNIQUE (namespace, predecessor_id),
    UNIQUE (namespace, successor_id),
    CHECK (predecessor_id <> successor_id),
    CHECK (original_transaction_id <> successor_id),
    CHECK ((generation = 1 AND predecessor_id = original_transaction_id)
        OR (generation > 1 AND predecessor_id <> original_transaction_id))
);

CREATE FUNCTION public.guard_evergreen_checkout_lineage() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Checkout lineage is immutable history';
    ELSIF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - 'runtime_state' - 'runtime_reason') IS DISTINCT FROM
           (to_jsonb(OLD) - 'runtime_state' - 'runtime_reason') THEN
            RAISE EXCEPTION 'Checkout lineage evidence is immutable';
        END IF;
    ELSIF NEW.generation > 1 AND NOT EXISTS (
        SELECT 1 FROM public.evergreen_checkout_lineage prior
        WHERE prior.namespace = NEW.namespace
          AND prior.original_transaction_id = NEW.original_transaction_id
          AND prior.generation = NEW.generation - 1
          AND prior.successor_id = NEW.predecessor_id
    ) THEN
        RAISE EXCEPTION 'Checkout predecessor generation is missing';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_evergreen_checkout_lineage
    BEFORE INSERT OR UPDATE OR DELETE ON public.evergreen_checkout_lineage
    FOR EACH ROW EXECUTE FUNCTION public.guard_evergreen_checkout_lineage();

CREATE TABLE public.evergreen_checkout_resolution_events (
    event_id UUID PRIMARY KEY,
    namespace TEXT NOT NULL,
    alias_id UUID NOT NULL,
    original_transaction_id UUID NOT NULL,
    effective_transaction_id UUID NULL,
    generation INTEGER NOT NULL CHECK (generation >= 0),
    result TEXT NOT NULL CHECK (result IN ('RESOLVED','REJECTED')),
    reason_code TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_evergreen_checkout_events_alias
    ON public.evergreen_checkout_resolution_events (namespace, alias_id, occurred_at DESC);

COMMIT;
