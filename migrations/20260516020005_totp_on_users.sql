-- Phase 1: TOTP secret moves from app_settings to users (per-user shape).
-- The app_settings columns are NOT dropped yet (rollback safety; audit §1e).

BEGIN;

ALTER TABLE public.users ADD COLUMN totp_secret text;
ALTER TABLE public.users ADD COLUMN totp_enabled boolean NOT NULL DEFAULT false;

-- Copy the Phase 0 singleton's TOTP state onto the sentinel user.
-- After Task 5, app_settings has user_id PK; the lookup is by user_id.
UPDATE public.users u
SET totp_secret = s.totp_secret,
    totp_enabled = COALESCE(s.totp_enabled, false)
FROM public.app_settings s
WHERE u.id = s.user_id
  AND u.id = '00000000-0000-0000-0000-000000000001'::uuid;

COMMIT;
