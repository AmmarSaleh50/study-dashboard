-- Phase 4: per-user Row Level Security policies.
--
-- Policies reference the session GUC app.user_id, set by app middleware via
-- SET LOCAL app.user_id = ?. The bypass role currently used by the app
-- ignores RLS — these policies are inert until the connection role is
-- flipped to a non-BYPASSRLS role (operational task; see docs/RLS.md).

BEGIN;

-- Helper: extract user_id from session GUC. Returns NULL if unset (the
-- 'true' arg = missing_ok); policies treat NULL as "no rows visible".
-- Inline expression below; no need for a function.

-- ===== courses =====
CREATE POLICY courses_user_isolation ON public.courses
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== schedule_slots =====
CREATE POLICY schedule_slots_user_isolation ON public.schedule_slots
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== lectures =====
CREATE POLICY lectures_user_isolation ON public.lectures
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== study_topics =====
CREATE POLICY study_topics_user_isolation ON public.study_topics
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== deliverables =====
CREATE POLICY deliverables_user_isolation ON public.deliverables
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== tasks =====
CREATE POLICY tasks_user_isolation ON public.tasks
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== exams =====
CREATE POLICY exams_user_isolation ON public.exams
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== events =====
CREATE POLICY events_user_isolation ON public.events
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== file_index =====
CREATE POLICY file_index_user_isolation ON public.file_index
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== oauth_auth_codes =====
CREATE POLICY oauth_auth_codes_user_isolation ON public.oauth_auth_codes
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== oauth_tokens =====
CREATE POLICY oauth_tokens_user_isolation ON public.oauth_tokens
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== email_verifications =====
CREATE POLICY email_verifications_user_isolation ON public.email_verifications
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== password_resets =====
CREATE POLICY password_resets_user_isolation ON public.password_resets
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== app_settings (PK is user_id) =====
CREATE POLICY app_settings_user_isolation ON public.app_settings
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- ===== users — self-only =====
-- Signup + login flows need to look up by email; those happen as the
-- privileged role (bypass). For non-bypass role: user can see only their
-- own row.
CREATE POLICY users_self_only ON public.users
    USING (id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (id = current_setting('app.user_id', true)::uuid);

-- ===== oauth_clients (global) =====
-- No user_id; permissive policy so RLS doesn't block it.
CREATE POLICY oauth_clients_allow_all ON public.oauth_clients
    USING (true) WITH CHECK (true);

-- ===== auth_attempts (per-IP, no user_id) =====
-- Permissive — rate-limiter needs to read+write freely.
CREATE POLICY auth_attempts_allow_all ON public.auth_attempts
    USING (true) WITH CHECK (true);

COMMIT;
