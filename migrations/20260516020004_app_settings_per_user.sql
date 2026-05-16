-- Phase 1: app_settings becomes 1:1 with users.
-- The Phase 0 singleton row (id=1) is preserved with user_id = sentinel.
--
-- Steps:
--   1. Drop the singleton CHECK constraint.
--   2. Add user_id column with sentinel default (for backfilling the existing row).
--   3. Drop the DEFAULT immediately — app_settings always has user_id set explicitly going forward.
--   4. Drop the old id PK + column.
--   5. Make user_id the new PK with cascade to users.

BEGIN;

-- 1. Drop the singleton constraint.
ALTER TABLE public.app_settings DROP CONSTRAINT app_settings_singleton;

-- 2. Add user_id column with sentinel default for backfill.
ALTER TABLE public.app_settings
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- 3. Drop the default — app_settings is 1:1 with users; explicit set going forward.
ALTER TABLE public.app_settings ALTER COLUMN user_id DROP DEFAULT;

-- 4. Drop the old id PK + column.
ALTER TABLE public.app_settings DROP CONSTRAINT app_settings_pkey;
ALTER TABLE public.app_settings DROP COLUMN id;

-- 5. New PK is user_id.
ALTER TABLE public.app_settings ADD CONSTRAINT app_settings_pkey
    PRIMARY KEY (user_id);

COMMIT;
