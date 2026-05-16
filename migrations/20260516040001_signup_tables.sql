-- Phase 3: tables for email verification + password reset tokens.
-- One-shot tokens. Verification has 24h expiry; password reset has 1h.
-- Used tokens are marked but retained (audit trail).

BEGIN;

CREATE TABLE public.email_verifications (
    token text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_email_verifications_user_id ON public.email_verifications(user_id);

CREATE TABLE public.password_resets (
    token text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_password_resets_user_id ON public.password_resets(user_id);

COMMIT;
