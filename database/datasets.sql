-- ============================================
-- DATAMIND AI
-- DATASET MANAGEMENT
-- ============================================

-- 1. Registro de bases de datos importadas

CREATE TABLE IF NOT EXISTS public.datasets (
    dataset_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    schema_name VARCHAR(63) NOT NULL UNIQUE,

    status VARCHAR(20) NOT NULL DEFAULT 'ready'
        CHECK (status IN ('processing', 'ready', 'failed')),

    table_count INTEGER NOT NULL DEFAULT 0
        CHECK (table_count >= 0),

    row_count BIGINT NOT NULL DEFAULT 0
        CHECK (row_count >= 0),

    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Registrar la base empresarial de demostración

INSERT INTO public.datasets (
    name,
    original_filename,
    schema_name,
    status,
    table_count,
    is_builtin
)
VALUES (
    'Base empresarial de demostración',
    'seed.sql',
    'public',
    'ready',
    5,
    TRUE
)
ON CONFLICT (schema_name) DO NOTHING;

-- 3. Asociar el historial con los datasets

ALTER TABLE public.query_history
ADD COLUMN IF NOT EXISTS dataset_id BIGINT;

-- 4. Relación entre historial y datasets

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_query_history_dataset'
          AND conrelid = 'public.query_history'::regclass
    ) THEN
        ALTER TABLE public.query_history
        ADD CONSTRAINT fk_query_history_dataset
        FOREIGN KEY (dataset_id)
        REFERENCES public.datasets(dataset_id)
        ON DELETE CASCADE;
    END IF;
END $$;

-- 5. Asociar el historial existente con la base de demostración

UPDATE public.query_history
SET dataset_id = (
    SELECT dataset_id
    FROM public.datasets
    WHERE schema_name = 'public'
)
WHERE dataset_id IS NULL;

-- 6. Exigir que cada consulta pertenezca a un dataset

ALTER TABLE public.query_history
ALTER COLUMN dataset_id SET NOT NULL;

-- 7. Índice para consultar rápidamente el historial

CREATE INDEX IF NOT EXISTS idx_query_history_dataset_created
ON public.query_history (dataset_id, created_at DESC);
