-- Phase 2: drop the sentinel DEFAULT from every owned table's user_id.
-- Services now pass user_id explicitly. An INSERT that forgets user_id
-- should error loudly, not silently default to the operator.
--
-- app_settings.user_id had its DEFAULT dropped in Phase 1 (Task 5).

BEGIN;

ALTER TABLE public.courses ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.schedule_slots ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.lectures ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.study_topics ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.deliverables ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.tasks ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.exams ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.events ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.file_index ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.oauth_auth_codes ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE public.oauth_tokens ALTER COLUMN user_id DROP DEFAULT;

COMMIT;
