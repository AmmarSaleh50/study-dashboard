-- Phase 6: per-user encrypted secrets table.
--
-- 1:1 with users. Telegram creds first; future columns (Moodle, Stripe)
-- get added in later phases as needed.
--
-- *_enc columns store Fernet-encrypted ciphertext (bytea). The
-- app/services/secrets.py helpers handle encrypt/decrypt; this table
-- never stores plaintext.

BEGIN;

CREATE TABLE public.user_secrets (
    user_id uuid PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    telegram_bot_token_enc bytea,
    telegram_chat_id text,
    telegram_webhook_secret_enc bytea,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- RLS: same shape as app_settings (1:1 with users).
ALTER TABLE public.user_secrets ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_secrets_user_isolation ON public.user_secrets
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- Index on telegram_chat_id for the webhook's chat_id → user_id lookup.
CREATE INDEX idx_user_secrets_telegram_chat_id ON public.user_secrets(telegram_chat_id)
    WHERE telegram_chat_id IS NOT NULL;

COMMIT;
