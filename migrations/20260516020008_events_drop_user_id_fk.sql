-- Phase 1 follow-up: drop the FK from events.user_id -> users(id).
--
-- Same root cause as the Phase 0 events.course_code FK drop (commit 5438b83):
-- the log_table_change() trigger fires during CASCADE deletes and tries to
-- insert audit events for rows whose parent (users / courses) is being
-- deleted in the same statement. The FK rejects the audit INSERT and the
-- whole cascade fails.
--
-- Fix: drop the FK. Audit logs should outlive their subjects; events.user_id
-- becomes denormalized informational text after the user is gone, same as
-- events.course_code today.
--
-- events.user_id stays NOT NULL — every audit row still captures a user_id
-- at insert time (via the trigger or explicit caller).

BEGIN;
ALTER TABLE public.events DROP CONSTRAINT IF EXISTS events_user_id_fkey;
COMMIT;
