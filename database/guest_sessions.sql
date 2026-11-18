BEGIN;

-- Identificar datasets pertenecientes a visitantes
ALTER TABLE public.datasets
ADD COLUMN IF NOT EXISTS guest_session_id UUID;

-- Fecha de vencimiento de los datasets temporales
ALTER TABLE public.datasets
ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Asociar el historial con una cuenta registrada
ALTER TABLE public.query_history
ADD COLUMN IF NOT EXISTS user_id BIGINT;

-- Relación con la tabla de usuarios
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_query_history_user'
          AND conrelid = 'public.query_history'::regclass
    ) THEN
        ALTER TABLE public.query_history
        ADD CONSTRAINT fk_query_history_user
        FOREIGN KEY (user_id)
        REFERENCES public.users(user_id)
        ON DELETE CASCADE;
    END IF;
END $$;

-- Índices para localizar los datasets temporales
CREATE INDEX IF NOT EXISTS idx_datasets_guest_session
ON public.datasets(guest_session_id);

CREATE INDEX IF NOT EXISTS idx_datasets_expires_at
ON public.datasets(expires_at)
WHERE expires_at IS NOT NULL;

-- Índice para consultar el historial de cada usuario
CREATE INDEX IF NOT EXISTS idx_query_history_user_dataset_created
ON public.query_history(user_id, dataset_id, created_at DESC);

COMMIT;
