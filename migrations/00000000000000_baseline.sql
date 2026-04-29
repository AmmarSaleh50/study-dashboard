-- Initial schema. Applied once on a fresh database; new migrations stack
-- on top with timestamps strictly greater than this one and run via
-- scripts/run_migrations.py. Earlier development history (the incremental
-- migrations that produced this snapshot) is preserved under
-- migrations/_archive/ for reference but is not part of the active set.

--
-- PostgreSQL database dump
--

\restrict TRb43unSFk1rdXSu1NnVCqoVSZm2125BB7WFm91H1u44DIQj4rcl9vxI5jRyspV

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.9

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--
-- IF NOT EXISTS added to this line (only) so the dump is applicable to a
-- freshly-initialised postgres, which always ships with `public` already
-- created. pg_dump itself emits a bare `CREATE SCHEMA public;` because it
-- assumes a `--clean` restore where that schema was just dropped.

CREATE SCHEMA IF NOT EXISTS public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: log_table_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.log_table_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE
  payload jsonb;
  row_id text;
  course_code text;
  kind text;
BEGIN
  -- Extract id (uuid or composite key) best-effort
  IF TG_OP = 'DELETE' THEN
    BEGIN row_id := (row_to_json(OLD)::jsonb->>'id'); EXCEPTION WHEN OTHERS THEN row_id := NULL; END;
    BEGIN course_code := (row_to_json(OLD)::jsonb->>'course_code'); EXCEPTION WHEN OTHERS THEN course_code := NULL; END;
    payload := jsonb_build_object(
      'table', TG_TABLE_NAME,
      'op', TG_OP,
      'id', row_id,
      'before', to_jsonb(OLD)
    );
  ELSE
    BEGIN row_id := (row_to_json(NEW)::jsonb->>'id'); EXCEPTION WHEN OTHERS THEN row_id := NULL; END;
    BEGIN course_code := (row_to_json(NEW)::jsonb->>'course_code'); EXCEPTION WHEN OTHERS THEN course_code := NULL; END;
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

  INSERT INTO public.events (kind, course_code, payload)
  VALUES (kind, course_code, payload);

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;


--
-- Name: rls_auto_enable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.rls_auto_enable() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$$;


--
-- Name: search_files(text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.search_files(q text, lim integer DEFAULT 20) RETURNS TABLE(path text, course_code text, size bigint, rank real, snippet text)
    LANGUAGE sql STABLE
    AS $$
  WITH query AS (
    SELECT websearch_to_tsquery('simple', q) AS tsq
  )
  SELECT
    f.path,
    f.course_code,
    f.size,
    ts_rank(f.search_vector, query.tsq) AS rank,
    ts_headline(
      'simple',
      f.text_content,
      query.tsq,
      'StartSel=<<,StopSel=>>,MaxFragments=2,MaxWords=15,MinWords=5,FragmentDelimiter=" … "'
    ) AS snippet
  FROM file_index f, query
  WHERE f.search_vector @@ query.tsq
  ORDER BY rank DESC
  LIMIT lim;
$$;


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
begin
  new.updated_at := now();
  return new;
end;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: app_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_settings (
    id smallint DEFAULT 1 NOT NULL,
    display_name text,
    monogram text,
    institution text,
    semester_label text,
    semester_start date,
    semester_end date,
    timezone text DEFAULT 'UTC'::text,
    locale text DEFAULT 'en-US'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    theme text DEFAULT 'editorial'::text,
    totp_secret text,
    totp_enabled boolean DEFAULT false NOT NULL,
    CONSTRAINT app_settings_singleton CHECK ((id = 1))
);


--
-- Name: courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.courses (
    code text NOT NULL,
    full_name text NOT NULL,
    short_name text,
    module_code text,
    ects integer,
    prof text,
    status_kind text,
    language text,
    color_hex text,
    folder_name text,
    exam_weight integer DEFAULT 100,
    exam_retries integer,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: deliverables; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.deliverables (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_code text,
    kind text,
    name text NOT NULL,
    available_at timestamp with time zone,
    due_at timestamp with time zone NOT NULL,
    status text DEFAULT 'open'::text,
    local_path text,
    external_url text,
    weight_info text,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    kind text NOT NULL,
    course_code text,
    payload jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: exams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exams (
    course_code text NOT NULL,
    scheduled_at timestamp with time zone,
    duration_min integer,
    location text,
    structure text,
    aids_allowed text,
    status text DEFAULT 'planned'::text,
    weight_pct integer DEFAULT 100,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: file_index; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_index (
    path text NOT NULL,
    course_code text,
    size bigint,
    sha256 text,
    text_content text,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, COALESCE(text_content, ''::text))) STORED,
    indexed_at timestamp with time zone DEFAULT now()
);


--
-- Name: lectures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lectures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_code text,
    number integer,
    held_on date,
    kind text DEFAULT 'lecture'::text,
    title text,
    summary text,
    attended boolean DEFAULT false,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: login_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.login_attempts (
    id bigint NOT NULL,
    ip text NOT NULL,
    ok boolean NOT NULL,
    user_agent text,
    at timestamp with time zone DEFAULT now()
);


--
-- Name: login_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.login_attempts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: login_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.login_attempts_id_seq OWNED BY public.login_attempts.id;


--
-- Name: oauth_auth_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_auth_codes (
    code text NOT NULL,
    client_id text NOT NULL,
    redirect_uri text NOT NULL,
    code_challenge text NOT NULL,
    code_challenge_method text DEFAULT 'S256'::text NOT NULL,
    scope text,
    expires_at timestamp with time zone NOT NULL,
    used boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: oauth_clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_clients (
    client_id text NOT NULL,
    client_secret text,
    client_name text NOT NULL,
    redirect_uris text[] NOT NULL,
    token_endpoint_auth_method text DEFAULT 'none'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: oauth_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_tokens (
    token text NOT NULL,
    client_id text NOT NULL,
    scope text,
    expires_at timestamp with time zone,
    revoked boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: schedule_slots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schedule_slots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_code text,
    kind text NOT NULL,
    weekday integer NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    room text,
    person text,
    starts_on date,
    ends_on date,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT schedule_slots_weekday_check CHECK (((weekday >= 1) AND (weekday <= 7)))
);


--
-- Name: study_topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.study_topics (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_code text,
    chapter text,
    name text NOT NULL,
    kind text,
    covered_on date,
    status text DEFAULT 'not_started'::text,
    confidence integer,
    last_reviewed_at timestamp with time zone,
    notes text,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    lecture_id uuid,
    description text,
    CONSTRAINT study_topics_confidence_check CHECK (((confidence >= 0) AND (confidence <= 5)))
);


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_code text,
    title text NOT NULL,
    description text,
    due_at timestamp with time zone,
    status text DEFAULT 'open'::text,
    priority text DEFAULT 'med'::text,
    tags text[],
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: login_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_attempts ALTER COLUMN id SET DEFAULT nextval('public.login_attempts_id_seq'::regclass);


--
-- Name: app_settings app_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_settings
    ADD CONSTRAINT app_settings_pkey PRIMARY KEY (id);


--
-- Name: courses courses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (code);


--
-- Name: deliverables deliverables_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deliverables
    ADD CONSTRAINT deliverables_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: file_index file_index_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_index
    ADD CONSTRAINT file_index_pkey PRIMARY KEY (path);


--
-- Name: exams klausuren_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exams
    ADD CONSTRAINT klausuren_pkey PRIMARY KEY (course_code);


--
-- Name: lectures lectures_course_kind_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lectures
    ADD CONSTRAINT lectures_course_kind_number_key UNIQUE (course_code, kind, number);


--
-- Name: lectures lectures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lectures
    ADD CONSTRAINT lectures_pkey PRIMARY KEY (id);


--
-- Name: login_attempts login_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_attempts
    ADD CONSTRAINT login_attempts_pkey PRIMARY KEY (id);


--
-- Name: oauth_auth_codes oauth_auth_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_auth_codes
    ADD CONSTRAINT oauth_auth_codes_pkey PRIMARY KEY (code);


--
-- Name: oauth_clients oauth_clients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_pkey PRIMARY KEY (client_id);


--
-- Name: oauth_tokens oauth_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT oauth_tokens_pkey PRIMARY KEY (token);


--
-- Name: schedule_slots schedule_slots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_slots
    ADD CONSTRAINT schedule_slots_pkey PRIMARY KEY (id);


--
-- Name: study_topics study_topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.study_topics
    ADD CONSTRAINT study_topics_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: file_index_course_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX file_index_course_idx ON public.file_index USING btree (course_code);


--
-- Name: file_index_search_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX file_index_search_idx ON public.file_index USING gin (search_vector);


--
-- Name: idx_deliverables_course; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deliverables_course ON public.deliverables USING btree (course_code);


--
-- Name: idx_deliverables_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deliverables_due ON public.deliverables USING btree (due_at);


--
-- Name: idx_events_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_created ON public.events USING btree (created_at DESC);


--
-- Name: idx_lectures_course; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lectures_course ON public.lectures USING btree (course_code);


--
-- Name: idx_lectures_held_on; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lectures_held_on ON public.lectures USING btree (held_on);


--
-- Name: idx_login_attempts_ip_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_login_attempts_ip_at ON public.login_attempts USING btree (ip, at DESC);


--
-- Name: idx_schedule_slots_course; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedule_slots_course ON public.schedule_slots USING btree (course_code);


--
-- Name: idx_study_topics_course; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_study_topics_course ON public.study_topics USING btree (course_code);


--
-- Name: idx_study_topics_lecture; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_study_topics_lecture ON public.study_topics USING btree (lecture_id);


--
-- Name: idx_study_topics_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_study_topics_status ON public.study_topics USING btree (status);


--
-- Name: idx_tasks_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_due ON public.tasks USING btree (due_at);


--
-- Name: idx_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_status ON public.tasks USING btree (status);


--
-- Name: oauth_auth_codes_expires_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX oauth_auth_codes_expires_idx ON public.oauth_auth_codes USING btree (expires_at);


--
-- Name: oauth_tokens_client_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX oauth_tokens_client_idx ON public.oauth_tokens USING btree (client_id);


--
-- Name: courses trg_log_change_courses; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_courses AFTER INSERT OR DELETE OR UPDATE ON public.courses FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: deliverables trg_log_change_deliverables; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_deliverables AFTER INSERT OR DELETE OR UPDATE ON public.deliverables FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: exams trg_log_change_klausuren; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_klausuren AFTER INSERT OR DELETE OR UPDATE ON public.exams FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: lectures trg_log_change_lectures; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_lectures AFTER INSERT OR DELETE OR UPDATE ON public.lectures FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: schedule_slots trg_log_change_schedule_slots; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_schedule_slots AFTER INSERT OR DELETE OR UPDATE ON public.schedule_slots FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: study_topics trg_log_change_study_topics; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_study_topics AFTER INSERT OR DELETE OR UPDATE ON public.study_topics FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: tasks trg_log_change_tasks; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_change_tasks AFTER INSERT OR DELETE OR UPDATE ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.log_table_change();


--
-- Name: courses trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.courses FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: deliverables trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.deliverables FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: exams trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.exams FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: lectures trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.lectures FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: schedule_slots trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.schedule_slots FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: study_topics trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.study_topics FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: tasks trg_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_updated_at BEFORE UPDATE ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: deliverables deliverables_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deliverables
    ADD CONSTRAINT deliverables_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE CASCADE;


--
-- Name: events events_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE SET NULL;


--
-- Name: exams klausuren_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exams
    ADD CONSTRAINT klausuren_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE CASCADE;


--
-- Name: lectures lectures_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lectures
    ADD CONSTRAINT lectures_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE CASCADE;


--
-- Name: oauth_auth_codes oauth_auth_codes_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_auth_codes
    ADD CONSTRAINT oauth_auth_codes_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(client_id) ON DELETE CASCADE;


--
-- Name: oauth_tokens oauth_tokens_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT oauth_tokens_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(client_id) ON DELETE CASCADE;


--
-- Name: schedule_slots schedule_slots_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_slots
    ADD CONSTRAINT schedule_slots_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE CASCADE;


--
-- Name: study_topics study_topics_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.study_topics
    ADD CONSTRAINT study_topics_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE CASCADE;


--
-- Name: study_topics study_topics_lecture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.study_topics
    ADD CONSTRAINT study_topics_lecture_id_fkey FOREIGN KEY (lecture_id) REFERENCES public.lectures(id) ON DELETE SET NULL;


--
-- Name: tasks tasks_course_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_course_code_fkey FOREIGN KEY (course_code) REFERENCES public.courses(code) ON DELETE SET NULL;


--
-- Name: app_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: courses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;

--
-- Name: deliverables; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.deliverables ENABLE ROW LEVEL SECURITY;

--
-- Name: events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

--
-- Name: exams; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.exams ENABLE ROW LEVEL SECURITY;

--
-- Name: file_index; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.file_index ENABLE ROW LEVEL SECURITY;

--
-- Name: lectures; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.lectures ENABLE ROW LEVEL SECURITY;

--
-- Name: login_attempts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.login_attempts ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_auth_codes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.oauth_auth_codes ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_clients; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.oauth_clients ENABLE ROW LEVEL SECURITY;

--
-- Name: oauth_tokens; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.oauth_tokens ENABLE ROW LEVEL SECURITY;

--
-- Name: schedule_slots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.schedule_slots ENABLE ROW LEVEL SECURITY;

--
-- Name: study_topics; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.study_topics ENABLE ROW LEVEL SECURITY;

--
-- Name: tasks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict TRb43unSFk1rdXSu1NnVCqoVSZm2125BB7WFm91H1u44DIQj4rcl9vxI5jRyspV

