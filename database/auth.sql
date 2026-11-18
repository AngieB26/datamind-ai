-- ============================================
-- DATAMIND AI
-- AUTHENTICATION AND DATASET OWNERSHIP
-- ============================================

CREATE TABLE IF NOT EXISTS public.users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
ON public.users (LOWER(email));

ALTER TABLE public.datasets
ADD COLUMN IF NOT EXISTS owner_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_datasets_owner'
          AND conrelid = 'public.datasets'::regclass
    ) THEN
        ALTER TABLE public.datasets
        ADD CONSTRAINT fk_datasets_owner
        FOREIGN KEY (owner_id)
        REFERENCES public.users(user_id)
        ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_datasets_owner
ON public.datasets(owner_id);

UPDATE public.datasets
SET owner_id = NULL
WHERE is_builtin = TRUE;
