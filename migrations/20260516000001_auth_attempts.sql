-- Rename login_attempts → auth_attempts; add `kind` so signup can share the table.
-- Phase 0: only kind='login' is written. Phase 3 adds kind='signup' + kind='reset'.
BEGIN;

ALTER TABLE public.login_attempts RENAME TO auth_attempts;
ALTER TABLE public.auth_attempts ADD COLUMN kind text NOT NULL DEFAULT 'login';
ALTER TABLE public.auth_attempts ADD CONSTRAINT auth_attempts_kind_check CHECK (kind IN ('login', 'signup', 'reset'));

-- Backfill is automatic via DEFAULT 'login'; existing rows pick that up on ALTER.

-- Index for the per-(ip, kind, window) hot path.
DROP INDEX IF EXISTS public.idx_login_attempts_ip_at;
CREATE INDEX idx_auth_attempts_ip_kind_at ON public.auth_attempts(ip, kind, at);

COMMIT;
