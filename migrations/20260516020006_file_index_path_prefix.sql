-- Phase 1: prefix every file_index.path with the user's id.
-- Pairs with scripts/migrate_study_root.sh (Task 8) which moves the files
-- on disk to match.
--
-- Idempotency guard: skip rows already prefixed.

BEGIN;

UPDATE public.file_index
SET path = user_id::text || '/' || path
WHERE NOT path LIKE user_id::text || '/%';

COMMIT;
