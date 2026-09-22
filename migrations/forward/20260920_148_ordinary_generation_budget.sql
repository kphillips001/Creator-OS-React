-- Session 1: additive ledger. Never backfill or reopen historical operations.
CREATE TABLE ordinary_generation_policy (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    installed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO ordinary_generation_policy DEFAULT VALUES;
CREATE TABLE ordinary_generation_budgets (
    operation_id uuid PRIMARY KEY REFERENCES ordinary_chat_reply_operations(operation_id),
    version text NOT NULL DEFAULT 'ORDINARY_RECOVERY_V1',
    candidate_count integer NOT NULL DEFAULT 0 CHECK(candidate_count BETWEEN 0 AND 2),
    provider_attempt_count integer NOT NULL DEFAULT 0 CHECK(provider_attempt_count BETWEEN 0 AND 3),
    initial_started boolean NOT NULL DEFAULT false,
    correction_started boolean NOT NULL DEFAULT false,
    obligation jsonb NOT NULL DEFAULT '{}'::jsonb,
    context_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    events jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION guard_ordinary_generation_budget() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.operation_id<>OLD.operation_id OR NEW.candidate_count<OLD.candidate_count
       OR NEW.provider_attempt_count<OLD.provider_attempt_count
       OR (OLD.initial_started AND NOT NEW.initial_started)
       OR (OLD.correction_started AND NOT NEW.correction_started) THEN
        RAISE EXCEPTION 'Ordinary generation lifetime budget cannot be reset' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ordinary_generation_budget_monotonic BEFORE UPDATE ON ordinary_generation_budgets
    FOR EACH ROW EXECUTE FUNCTION guard_ordinary_generation_budget();
