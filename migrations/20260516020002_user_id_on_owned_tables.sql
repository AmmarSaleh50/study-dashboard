-- Phase 1: add user_id to every owned table, defaulting to the operator
-- sentinel. The DEFAULT keeps Phase 0 services working (no INSERT site
-- has to know about user_id yet); Phase 2 drops the DEFAULT when services
-- pass user_id explicitly.
--
-- NOT NULL is enforced from the start because the DEFAULT covers it.

BEGIN;

-- courses
ALTER TABLE public.courses
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- schedule_slots
ALTER TABLE public.schedule_slots
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- lectures
ALTER TABLE public.lectures
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- study_topics
ALTER TABLE public.study_topics
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- deliverables
ALTER TABLE public.deliverables
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- tasks
ALTER TABLE public.tasks
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- exams
ALTER TABLE public.exams
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- events
ALTER TABLE public.events
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- file_index
ALTER TABLE public.file_index
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- oauth_auth_codes
ALTER TABLE public.oauth_auth_codes
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- oauth_tokens
ALTER TABLE public.oauth_tokens
    ADD COLUMN user_id uuid NOT NULL
        DEFAULT '00000000-0000-0000-0000-000000000001'::uuid
        REFERENCES public.users(id) ON DELETE CASCADE;

-- Indexes for the per-user filter hot paths.
CREATE INDEX idx_courses_user_id ON public.courses(user_id);
CREATE INDEX idx_schedule_slots_user_id ON public.schedule_slots(user_id);
CREATE INDEX idx_lectures_user_id ON public.lectures(user_id);
CREATE INDEX idx_study_topics_user_id ON public.study_topics(user_id);
CREATE INDEX idx_deliverables_user_id ON public.deliverables(user_id);
CREATE INDEX idx_tasks_user_id ON public.tasks(user_id);
CREATE INDEX idx_exams_user_id ON public.exams(user_id);
CREATE INDEX idx_events_user_id ON public.events(user_id);
CREATE INDEX idx_file_index_user_id ON public.file_index(user_id);
CREATE INDEX idx_oauth_auth_codes_user_id ON public.oauth_auth_codes(user_id);
CREATE INDEX idx_oauth_tokens_user_id ON public.oauth_tokens(user_id);

COMMIT;
