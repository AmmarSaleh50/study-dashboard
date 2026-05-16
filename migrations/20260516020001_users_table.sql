-- Phase 1: create the users table and seed the operator row.
--
-- The seed uses the Phase 0 sentinel UUID (matches app.auth.SENTINEL_USER_ID's
-- default). Self-hosters who set OPERATOR_USER_ID to a different UUID must
-- also UPDATE this row post-deploy. Phase 3 makes the email/password
-- editable via the Settings UI.

BEGIN;

CREATE EXTENSION IF NOT EXISTS citext SCHEMA public;

CREATE TABLE public.users (
    id            uuid PRIMARY KEY,
    email         public.citext NOT NULL UNIQUE,
    password_hash text,
    display_name  text NOT NULL DEFAULT 'User',
    email_verified_at timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

-- Seed the operator row. Idempotent via ON CONFLICT.
INSERT INTO public.users (id, email, display_name, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'operator@local',
    'Operator',
    now()
)
ON CONFLICT (id) DO NOTHING;

COMMIT;
