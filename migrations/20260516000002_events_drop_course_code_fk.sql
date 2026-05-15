-- Drop the FK from events.course_code -> courses(code).
-- Reason: the log_table_change() trigger inserts into events during
-- CASCADE deletes of courses; the parent course row is already gone by
-- the time the trigger fires on child rows, so the FK rejects the audit
-- INSERT and the whole cascade fails. Audit logs should outlive their
-- subjects — course_code becomes denormalized informational text.
BEGIN;
ALTER TABLE public.events DROP CONSTRAINT IF EXISTS events_course_code_fkey;
COMMIT;
