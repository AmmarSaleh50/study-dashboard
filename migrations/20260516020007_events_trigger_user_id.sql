-- Phase 1: log_table_change trigger now populates events.user_id from
-- the OLD/NEW row's user_id column. All existing logic (kind format,
-- course_code extraction, payload shape, SECURITY DEFINER, search_path)
-- preserved byte-for-byte from the baseline.

BEGIN;

CREATE OR REPLACE FUNCTION public.log_table_change()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $$
DECLARE
  payload jsonb;
  row_id text;
  course_code text;
  user_id uuid;
  kind text;
BEGIN
  -- Extract id (uuid or composite key) best-effort
  IF TG_OP = 'DELETE' THEN
    BEGIN row_id := (row_to_json(OLD)::jsonb->>'id'); EXCEPTION WHEN OTHERS THEN row_id := NULL; END;
    BEGIN course_code := (row_to_json(OLD)::jsonb->>'course_code'); EXCEPTION WHEN OTHERS THEN course_code := NULL; END;
    BEGIN user_id := (row_to_json(OLD)::jsonb->>'user_id')::uuid; EXCEPTION WHEN OTHERS THEN user_id := NULL; END;
    payload := jsonb_build_object(
      'table', TG_TABLE_NAME,
      'op', TG_OP,
      'id', row_id,
      'before', to_jsonb(OLD)
    );
  ELSE
    BEGIN row_id := (row_to_json(NEW)::jsonb->>'id'); EXCEPTION WHEN OTHERS THEN row_id := NULL; END;
    BEGIN course_code := (row_to_json(NEW)::jsonb->>'course_code'); EXCEPTION WHEN OTHERS THEN course_code := NULL; END;
    BEGIN user_id := (row_to_json(NEW)::jsonb->>'user_id')::uuid; EXCEPTION WHEN OTHERS THEN user_id := NULL; END;
    IF TG_OP = 'UPDATE' THEN
      payload := jsonb_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'id', row_id,
        'before', to_jsonb(OLD),
        'after', to_jsonb(NEW)
      );
    ELSE
      payload := jsonb_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'id', row_id,
        'after', to_jsonb(NEW)
      );
    END IF;
  END IF;

  kind := 'db:' || lower(TG_OP) || ':' || TG_TABLE_NAME;

  INSERT INTO public.events (kind, course_code, user_id, payload)
  VALUES (kind, course_code, user_id, payload);

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;

COMMIT;
