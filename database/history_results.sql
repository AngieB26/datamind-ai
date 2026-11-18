ALTER TABLE public.query_history
ADD COLUMN IF NOT EXISTS result_columns JSONB
NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.query_history
ADD COLUMN IF NOT EXISTS result_rows JSONB
NOT NULL DEFAULT '[]'::jsonb;

-- Permitir al usuario del historial actualizar sus registros
-- para guardar y reconstruir resultados.
GRANT UPDATE ON TABLE public.query_history
TO datamind_history;