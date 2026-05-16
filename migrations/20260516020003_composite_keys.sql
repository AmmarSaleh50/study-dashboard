-- Phase 1: composite PKs and FKs lock per-user data integrity at the schema layer.
--
-- After this migration:
--   - courses PK is (user_id, code) — two users can have a "MATH" course each.
--   - Every child FK to courses is composite (user_id, course_code).
--   - Cross-user FK references become structurally impossible.
--   - exams PK is (user_id, course_code). file_index PK is (user_id, path).
--
-- Order matters: Postgres won't let us drop courses_pkey while any child FK
-- still depends on it. We drop ALL child FKs first, then swap the PK, then
-- re-add the composite FKs against the new (user_id, code) target.

BEGIN;

-- ===== Step 1: drop every FK that references courses(code) =====
ALTER TABLE public.schedule_slots
    DROP CONSTRAINT schedule_slots_course_code_fkey;
ALTER TABLE public.lectures
    DROP CONSTRAINT lectures_course_code_fkey;
ALTER TABLE public.study_topics
    DROP CONSTRAINT study_topics_course_code_fkey;
ALTER TABLE public.deliverables
    DROP CONSTRAINT deliverables_course_code_fkey;
ALTER TABLE public.tasks
    DROP CONSTRAINT tasks_course_code_fkey;
ALTER TABLE public.exams
    DROP CONSTRAINT klausuren_course_code_fkey;

-- ===== Step 2: swap PKs =====
-- courses: PK (code) -> PK (user_id, code)
ALTER TABLE public.courses DROP CONSTRAINT courses_pkey;
ALTER TABLE public.courses ADD CONSTRAINT courses_pkey
    PRIMARY KEY (user_id, code);

-- exams: PK (course_code) -> PK (user_id, course_code), rename away from klausuren_
ALTER TABLE public.exams DROP CONSTRAINT klausuren_pkey;
ALTER TABLE public.exams ADD CONSTRAINT exams_pkey
    PRIMARY KEY (user_id, course_code);

-- file_index: PK (path) -> PK (user_id, path)
ALTER TABLE public.file_index DROP CONSTRAINT file_index_pkey;
ALTER TABLE public.file_index ADD CONSTRAINT file_index_pkey
    PRIMARY KEY (user_id, path);

-- ===== Step 3: add composite FKs against the new courses PK =====
ALTER TABLE public.schedule_slots
    ADD CONSTRAINT schedule_slots_user_course_fkey
        FOREIGN KEY (user_id, course_code)
        REFERENCES public.courses(user_id, code)
        ON DELETE CASCADE;

ALTER TABLE public.lectures
    ADD CONSTRAINT lectures_user_course_fkey
        FOREIGN KEY (user_id, course_code)
        REFERENCES public.courses(user_id, code)
        ON DELETE CASCADE;

ALTER TABLE public.study_topics
    ADD CONSTRAINT study_topics_user_course_fkey
        FOREIGN KEY (user_id, course_code)
        REFERENCES public.courses(user_id, code)
        ON DELETE CASCADE;

ALTER TABLE public.deliverables
    ADD CONSTRAINT deliverables_user_course_fkey
        FOREIGN KEY (user_id, course_code)
        REFERENCES public.courses(user_id, code)
        ON DELETE CASCADE;

-- tasks.course_code is NULLable; preserve ON DELETE SET NULL semantics.
-- For composite FK with SET NULL we MUST restrict the SET NULL action to
-- (course_code) only — tasks.user_id is NOT NULL, so blanket SET NULL would
-- violate that constraint. Postgres 15+ supports the column subset syntax.
ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_user_course_fkey
        FOREIGN KEY (user_id, course_code)
        REFERENCES public.courses(user_id, code)
        ON DELETE SET NULL (course_code);

ALTER TABLE public.exams
    ADD CONSTRAINT exams_user_course_fkey
        FOREIGN KEY (user_id, course_code)
        REFERENCES public.courses(user_id, code)
        ON DELETE CASCADE;

COMMIT;
