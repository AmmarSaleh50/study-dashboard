# Changelog

All notable changes to OpenStudy will be documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [SemVer](https://semver.org/spec/v2.0.0.html).

## v0.7.0-pre.6 (unreleased) — Multi-tenant Phase 5

### MCP user binding
- `app/mcp_http.OAuthTokenVerifier.verify_token` now stamps the bearer's user_id into a contextvar, and populates `AccessToken.expires_at` from the token row (Bug E).
- `app/mcp_tools.py` (~46 tool call sites) now reads the per-request user via `_get_mcp_user_id()` instead of the global SENTINEL_USER_ID. Each MCP request now operates on its bearer's user data, not the operator's.

### OAuth hardening
- Consent flow now binds `state` + `client_id` + `code_challenge` to a signed `oauth_consent_state` cookie (HttpOnly, Secure, SameSite=Strict, 10-min TTL) issued at `/oauth/authorize` and verified at `/oauth/consent` (Bug F). Prevents same-site CSRF on the consent step.

### Schema
- Bulk-revoked all pre-Phase-5 oauth_tokens (force fresh consent so every active token has a real user_id).

### Tests
- New `tests/mcp/test_bearer_user_binding.py` proves cross-user MCP isolation + expires_at population.
- New `tests/test_oauth_consent_csrf.py` proves consent POSTs without/with-mismatch cookie are rejected.
- New regression in `tests/services/test_oauth.py::test_bulk_revoke_invalidates_all_tokens`.
- Suite total: 300 (was 289 at Phase 4).

## v0.7.0-pre.5 (unreleased) — Multi-tenant Phase 4

### Schema
- Per-user Row Level Security policies on every owned table. USING + WITH CHECK reference `current_setting('app.user_id', true)::uuid`.
- Permissive policies on global tables (`oauth_clients`, `auth_attempts`).
- `users` table policy is self-only by id.

### App
- `app/auth.py` adds a contextvar `_current_user_id`. `optional_user`/`require_user` stamp it on every authenticated request.
- `app/db.py` issues `SELECT set_config('app.user_id', ?, true)` on every connection acquire when the contextvar is set. Inert when unset (e.g., for unauthed health checks).
- Middleware in `app/main.py` clears the contextvar at the start of each HTTP request (defense against contextvar leakage in shared async tasks).

### Behaviour (unchanged today)
- The app currently connects as a BYPASSRLS role; policies are inert.
- App-side `WHERE user_id = $1` filters (Phase 2) remain the active enforcement.
- Flipping the prod connection role to a non-BYPASSRLS role activates the policies. See `docs/RLS.md`.

### Tests
- `tests/test_phase4_guc.py` — proves the contextvar reaches the GUC.
- `tests/test_phase4_rls.py` — uses `SET LOCAL ROLE` + a non-BYPASSRLS test role to prove policies enforce.
- Suite total: 289 (was 285 at Phase 3).

## v0.7.0-pre.4 (unreleased) — Multi-tenant Phase 3

### Backend
- New `app/services/email.py` with pluggable backends: `console` (test default) and `gmail_smtp` (Gmail app-password SMTP via stdlib smtplib).
- Email templates in `app/templates/email/` (Jinja2): verify_email + password_reset.
- New `app/services/auth_signup.py` with signup, verify_email, request_password_reset, complete_password_reset.
- New tables: `email_verifications` + `password_resets` (one-shot tokens with expires_at + used_at).
- New endpoints: `POST /auth/signup` (gated by `SIGNUPS_ENABLED`), `GET /auth/verify-email`, `POST /auth/forgot-password`, `POST /auth/reset-password`.
- `/auth/login` now accepts `email` + `password`. Operator-legacy (no email, password against `APP_PASSWORD_HASH`) retained for upgrade safety.
- Session cookie payload upgraded to JSON `{u: user_id, iat: timestamp}`. `optional_user`/`require_user` look up `users` row by id. Legacy `b"authed"` cookies fall back to the sentinel during rollout.

### Frontend
- Login form gains an email field.
- New routes: `/signup`, `/forgot-password`, `/reset-password`, `/verify-email`.
- 4 new mutations/queries in `web/src/lib/queries.ts`.

### Ops
- New `scripts/seed_operator_password.py` — reads `APP_PASSWORD_HASH` env, sets `users.password_hash` for the operator if NULL. Idempotent. Invoked by `deploy.sh` after `db push`.
- New env vars: `EMAIL_BACKEND`, `GMAIL_SMTP_USER`, `GMAIL_SMTP_APP_PASSWORD`, `EMAIL_FROM`, `EMAIL_FROM_NAME`, `SIGNUPS_ENABLED`, `PUBLIC_URL`. All have safe defaults; `EMAIL_BACKEND=console` keeps tests silent.

### Tests
- New `tests/test_integration_signup.py` (4 tests): full signup → verify → login → forgot → reset flow + signup-disabled + bad-token + no-enumeration.
- New `tests/services/test_email.py` (3 tests) + `tests/services/test_auth_signup.py` (7 tests) + `tests/routers/test_auth_signup.py` (6 tests).
- Suite total: 285 (was 262 at Phase 2).

### Migration notes
- After upgrade: existing operators continue to log in with their old password via the legacy fallback. Once `users.password_hash` is set (via `seed_operator_password.py` or `forgot-password` flow), the email-based login is the canonical path.
- Operator email defaults to `operator@local` (env-configurable via `OPERATOR_EMAIL`). To change, either UPDATE `users` directly or use the forgot-password flow.

## v0.7.0-pre.3 (unreleased) — Multi-tenant Phase 2

### Services
- Every service function now takes `user_id: UUID` as its first parameter.
- All SELECTs filter via `WHERE user_id = $1`. INSERTs include user_id. UPDATEs/DELETEs constrain by user_id (defense in depth).
- Intent layer forwards user_id to services (was accept-and-ignore in Phase 0).
- oauth service threads user_id from `/oauth/consent` through token issuance.
- Storage layer (`app/services/storage.py`) takes user_id and resolves paths under `STUDY_ROOT/<user_id>/...`. Path traversal is blocked at the user_root boundary.
- file_index search filters by user_id; index_all stays operator-scoped and walks per-user directories.

### Schema
- Dropped sentinel `DEFAULT` on every owned table's user_id column. INSERTs must now supply user_id explicitly; absence raises a NOT NULL violation rather than silently using the operator.

### Tests
- New `tests/test_phase2_isolation.py` (4 tests) proves the service filters genuinely isolate data between two users.
- Coverage tests in storage + file_index for cross-user traversal blocking and operator-scoped reindex.
- Suite total: 262 (was 255 at Phase 1).

### Behaviour
- App still operates single-tenant at the entry points — routers + MCP tools pass the sentinel UUID. Phase 3 (signup endpoints) makes user identity real via the session cookie.

## v0.7.0-pre.2 (unreleased) — Multi-tenant Phase 1

### Schema
- New `users` table with operator seed row (sentinel UUID, "operator@local").
- Every owned table now has `user_id NOT NULL FK to users(id) ON DELETE CASCADE` with a sentinel DEFAULT — Phase 0 services continue to work unchanged.
- Composite PKs and FKs lock per-user data integrity: `courses` PK is `(user_id, code)`; downstream FKs use `(user_id, course_code) → courses(user_id, code)`. Two users can have the same course code.
- `app_settings` is 1:1 with `users` (PK `user_id`, singleton constraint dropped, `id` column removed).
- TOTP secret moved from `app_settings` to `users` (audit §6). `app_settings.totp_*` columns retained for rollback safety.
- `file_index.path` prefixed with `<user_id>/`; idempotent.
- `events.user_id` populated by the `log_table_change()` trigger.
- `events.user_id` FK to users dropped — audit logs survive cascade deletes (same precedent as Phase 0's `events.course_code` drop).

### Behaviour (unchanged)
- App still operates single-tenant via the Phase 0 sentinel. Phase 2 wires services to filter by user_id; until then every INSERT uses the DEFAULT.

### Ops
- New env vars (optional, default to sentinel): `OPERATOR_USER_ID`, `OPERATOR_EMAIL`, `OPERATOR_DISPLAY_NAME`.
- `./deploy.sh` invokes `scripts/migrate_study_root.sh` after `db push` to move course folders into the operator subdirectory.

### Tests
- New `tests/test_phase1_schema.py` (4 tests) locks cascade-delete + composite-FK invariants.
- Suite total: 255 (was 250 at Phase 0).

## [v0.6.0] — 2026-04-29

**Internal hardening.** No user-visible feature changes. The PostgREST
service is gone — FastAPI now talks to Postgres directly via a `psycopg`
async pool — and the project finally has a real backend test suite (213
tests against a real Postgres testcontainer with per-test transaction
rollback). Plus a handful of correctness + security fixes surfaced by
the post-migration audits.

### Changed — architecture
- **Dropped PostgREST.** Backend services now use `psycopg[pool]` async
  pool directly. Pool is opened/closed in the FastAPI lifespan; every
  service module migrated to the new helpers (`db.fetch`, `db.fetchrow`,
  `db.fetchval`, `db.execute`, `db.db()`). One fewer container, one
  fewer hop, simpler error model. `POSTGREST_URL` / `POSTGREST_API_KEY` /
  `POSTGREST_AUTH` env vars removed; the pool reads `DATABASE_URL`
  directly. Stack is now three containers (postgres + openstudy +
  frontend), not four.
- **Auth code consumption is now atomic.** `oauth_svc.consume_auth_code`
  uses a single `DELETE … RETURNING *` rather than SELECT-then-UPDATE,
  closing the previous TOCTOU window where two parallel callers could
  both succeed with the same code.
- **Lecture-topics insertion is now transactional.** `add_lecture_topics`
  wraps the optional lecture create + every topic insert in one psycopg
  transaction — partial-failure rollback is now guaranteed.
- **`/api/health` no longer blocks the event loop.** Storage stat call
  moved off the request thread.
- **Rate limiter prefers `CF-Connecting-IP`** over `X-Forwarded-For` —
  Cloudflare's header is unspoofable from outside the tunnel; XFF is.

### Added — test infrastructure
- **pytest + testcontainers-postgres** with a per-test transaction
  rollback shim (`force_rollback=True` + a `_TxnPool` connection pin)
  so every test gets a clean DB without paying for container churn.
- **213 backend tests:** ~145 service-layer + 60 MCP-tool tests across
  11 files (one per entity family) + 5 helper unit tests + 3 multi-step
  end-to-end scenarios (`test_integration_full_flow.py` — full OAuth
  lifecycle, login rate-limit, TOTP enroll+login).
- **`app/services/_helpers.py::validated_cols`** — filters dict keys to
  Pydantic-declared schema fields before f-stringing into INSERT/UPDATE
  SQL. Defence in depth against future schema bugs that might inject
  unexpected keys; applied at all 16 patch/insert sites across 7 service
  files.

### Added — OAuth
- **`POST /oauth/revoke`** (RFC 7009) — public clients call this on
  logout. Endpoint is now advertised in `/.well-known/oauth-authorization-server`
  via `revocation_endpoint` and `revocation_endpoint_auth_methods_supported`.

### Fixed
- **`update_settings` patch flow** no longer overwrites valid timezone /
  locale fields with NULL when the caller passes `None` for unset
  parameters. The MCP `update_app_settings` tool was passing every
  parameter (including unset ones) through to `AppSettingsPatch`;
  `model_dump(exclude_none=True)` now matches the convention used by
  every other patch service. Surfaced by the new MCP-tool tests.
- **`update_settings` fallback insert** uses `ON CONFLICT (id) DO UPDATE`,
  so two concurrent first-callers don't race the PK constraint into a 500.
- **`/api/auth/totp/setup`** is now an upsert. On a fresh DB without an
  `app_settings` row, the previous bare UPDATE matched zero rows but
  returned 200 with a generated secret — `/totp/enable` then 400'd.
- **`consume_auth_code` rejects non-S256 PKCE** unconditionally. OAuth
  2.1 mandates S256; the previous code accepted `plain` if a code row
  somehow stored that method, which a direct POST to `/oauth/consent`
  could trigger by skipping the `/authorize` S256 check.
- **`record_event` ordering tie-breaker.** Two events inserted in the
  same transaction shared `created_at = now()` (transaction-scoped);
  switched to `clock_timestamp()` and added `id DESC` to the ORDER BY.
- **`storage._log` savepoint.** Wrapped the activity-log insert in an
  inner transaction so swallowed FK violations don't poison the outer
  request transaction.
- **Pool-level UUID loader.** psycopg returns UUID columns as `uuid.UUID`
  by default; Pydantic schemas expect `str`. Registered a text + binary
  protocol loader on the pool so every fetch returns strings, no
  per-service conversions.

### Removed
- **`postgrest-py` dependency.** Gone from `pyproject.toml` /
  `uv.lock`.
- **PostgREST container** from `docker-compose.yml`.
- **`app.db.client()` and the legacy postgrest helper.** All call sites
  migrated.

### Migration notes (upgrading from v0.5.0)

If you're running a v0.5.0 deploy:

1. Pull the new code, then run `./deploy.sh`. The deploy script now
   runs with `--remove-orphans` so the PostgREST container is cleaned
   up automatically.
2. `DATABASE_URL` must be set (it already was for migrations; nothing
   new here). `POSTGREST_URL` / `POSTGREST_API_KEY` / `POSTGREST_AUTH`
   are no longer read — safe to remove from `.env`.
3. No schema changes. The migration runner has nothing new to apply.

[v0.6.0]: https://github.com/openstudy-dev/OpenStudy/releases/tag/v0.6.0

## [v0.5.0] — 2026-04-26

**Self-hosted by default.** Big architectural shift: OpenStudy no longer
depends on Supabase or Vercel. The whole stack — Postgres, PostgREST,
FastAPI, and the React frontend — runs as four containers on any Docker
host, brought up with a single `./deploy.sh`. Course files live on a
bind-mounted directory instead of object storage, indexed locally for
full-text search. On top of the architectural move, this release also
ships a public landing page, brand identity, TOTP 2FA, and a Telegram
bot integration.

### Added — infrastructure
- **`docker-compose.yml`** — four-service stack on an internal bridge
  network: `openstudy-postgres` (Postgres 16-alpine), `openstudy-postgrest`
  (PostgREST 12.2.3, JWT auth disabled, only reachable from the network),
  `openstudy` (the FastAPI image built from `Dockerfile`), and
  `openstudy-frontend` (the React SPA served by an in-container Caddy).
  Only the frontend (`127.0.0.1:8080`) and FastAPI (`127.0.0.1:8000`) are
  bound to the host; an outer reverse proxy (Caddy / nginx / Traefik)
  forwards a single `127.0.0.1:8080` upstream.
- **`Dockerfile`** — `python:3.12-slim` base, uv-managed deps, multi-layer
  cache for fast rebuilds.
- **`web/Dockerfile`** — multi-stage build: Node 20 + pnpm builds the
  Vite SPA, then a `caddy:alpine` image serves it. The Caddyfile inside
  the image does SPA fallback (`try_files`) plus `reverse_proxy
  openstudy:8000` for `/api`, `/mcp`, `/oauth` paths.
- **`./deploy.sh`** — single-command deploy with rollback. Pre-flight →
  build both images → apply migrations → health-gate (`GET /api/health`
  polled for 60s) → rollback to the previous image if health doesn't go
  green. Flags: `--skip-build`, `--no-rollback`, `--status`, `--help`.
- **Migrations runner** (`scripts/run_migrations.py`) — idempotent,
  transactional, sha256-tracked. State lives in a `_migrations` table.
  Files under `migrations/` apply in filename order.
- **Initial schema as `migrations/00000000000000_baseline.sql`** —
  canonical starting point for fresh deployments. Earlier development
  history preserved under `migrations/_archive/` for reference.
- **Filesystem storage layer** (`app/services/storage.py`) — files live
  at `STUDY_ROOT` (default `/opt/courses`); the storage service does
  read / write / list / move / delete directly on disk. Browser file
  serving via new `/api/files/raw` and `/api/files/upload-target`
  endpoints (cookie-authenticated, same-origin).
- **Filesystem full-text index** (`app/services/file_index.py`,
  `scripts/index_files.py`, baked into the baseline migration): walks
  `STUDY_ROOT`, extracts text from PDFs / notebooks / markdown / typst,
  upserts into `file_index`. Search exposed as `GET /api/files/search`,
  backed by the `search_files` Postgres RPC for ranking + snippet
  generation in one round-trip.
- **`/api/health`** now checks dependencies (DB SELECT + storage stat)
  instead of returning a static `{ok: true}`.
- **`/api/internal/*`** router (`app/routers/internal.py`) —
  bearer-gated (`X-Internal-Secret`) endpoints for cron jobs to trigger
  reindex, plus a Telegram-bot webhook (authed via Telegram's own
  `X-Telegram-Bot-Api-Secret-Token` header) exposing `/sync`, `/status`,
  `/help` to the operator's allowlisted chat.

### Added — frontend & brand
- **Brand assets** — `web/public/brand/{mark,wordmark}/{on-light,on-dark}.svg`,
  rendered via the new `<Wordmark>` React component
  (`web/src/components/brand/wordmark.tsx`) and embedded in the README
  header.
- **Landing page** at `/` (`web/src/routes/landing.tsx` +
  `web/src/styles/landing.css`): hero with auto-rotating five-theme
  carousel, animated MCP / Day-0 demo, real Claude Desktop screenshots,
  self-host terminal block, GitHub-stars CTA, floating navbar that
  hides on scroll-down. All CTAs link to the GitHub repo — no waitlist
  or signup.
- **`VITE_SHOW_LANDING`** env flag (default `false`) — when `true`, `/`
  renders the landing page; when `false`, `/` redirects straight to the
  app (`/app` if signed in, `/login` otherwise). Self-hosters typically
  leave it off.
- **`scripts/build-seo.mjs`** — Vite prebuild step that regenerates
  `robots.txt`, `sitemap.xml`, and `manifest.webmanifest` from
  `VITE_SITE_URL` / `VITE_SITE_NAME`. Forks deploying to a custom domain
  get correct canonical URLs and PWA metadata without code edits.
- **SEO + PWA assets** — `web/public/og-card.png`, `apple-touch-icon.png`,
  `icon-192/256/512.png`, `security.txt`, `manifest.webmanifest`.
- **TOTP / 2FA** for the dashboard login
  (`web/src/components/settings/totp-card.tsx`, baked into the baseline
  migration). Setup-key + QR + recovery-code flow inside Settings.
- **Multi-language `<title>` and `<html lang>`** via
  `web/src/lib/document-head.ts` — switches between EN / DE based on
  the active i18n locale.

### Changed
- **`POSTGREST_URL` / `POSTGREST_API_KEY`** env vars replace
  `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`. Breaking change for anyone
  upgrading from v0.3.x — see migration notes below.
- **`POSTGREST_AUTH`** flag — set to `false` to skip Bearer auth headers
  when targeting a self-hosted PostgREST that has JWT validation off.
- **`app/db.py`** — function renamed `supabase()` → `client()`. All
  service files migrated to `from app.db import client`.
- **`/api/internal/sync`** — runs reindexing in a FastAPI background
  task instead of spawning subprocesses. The `mode` query parameter is
  still accepted (and echoed back) for caller compatibility, but no
  longer affects behaviour.
- **README**, **INSTALL.md**, **CONTRIBUTING.md**, **`.env.example`**
  all rewritten around the docker-compose deploy. README header shows
  the OpenStudy wordmark with auto light / dark variants instead of a
  plain heading; database badge updated from "Supabase Postgres" to
  "Postgres 16".
- **`PUBLIC_SITE_URL`** is the single source of truth for the domain
  baked into canonical / OG / sitemap / manifest tags. Previous default
  `openstudy.dev` removed; default is now `http://localhost:8080` so
  forks don't accidentally ship with someone else's domain.
- **`N8N_MOODLE_WEBHOOK_URL`** has no default any more — endpoints that
  use it 503 with a helpful message when unset, instead of trying to
  hit a hardcoded host.

### Removed
- **Vercel artefacts** — `vercel.json`, the `api/index.py` shim, related
  `.vercel/` config. Vercel was retired as a host; the "build dist +
  rsync to a static web server" deploy path is gone too.
- **Supabase-specific layout** — top-level `supabase/` folder. Migrations
  live under `migrations/` now.
- **Bucket-sync scripts** — `force_push_to_bucket.py`, `sync.py`,
  `openstudy.py`, the bidirectional CONFLICT-DEL-REMOTE state machine.
  With local filesystem storage there's nothing to mirror to a separate
  object store. Moved to `scripts/_deprecated/` for reference.
- **`TRADEMARK.md`** — the project ships under MIT only, with no
  separate trademark policy. Self-host rebranding guidance now lives
  in CONTRIBUTING.md (`VITE_SITE_URL` / `VITE_SITE_NAME` + brand assets).

### Migration notes (upgrading from v0.3.x)

This is a breaking release. If you're moving an existing OpenStudy
install over from Supabase + Vercel:

1. `pg_dump` your Supabase database and restore it into the new local
   Postgres before first running `./deploy.sh` against real users — see
   [INSTALL.md §4](./INSTALL.md#restoring-data-into-a-fresh-box).
2. Rename `SUPABASE_URL` → `POSTGREST_URL` and `SUPABASE_SERVICE_KEY` →
   `POSTGREST_API_KEY` in your `.env`. Add a new `.env.docker` next to
   it with `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` for the
   database container.
3. Move your course files into the path you'll mount as `STUDY_ROOT` in
   the compose file (default `/opt/courses`).
4. Make sure the `courses.folder_name` column is populated for every
   course — it's now the source of truth that `/api/files/lecture-materials`
   and the file browser use to map a course code to its on-disk folder
   (replaces the previously hardcoded mapping).
5. Drop your Vercel deployment once the new docker host is healthy.
   Point your domain at the new outer reverse proxy.

## [v0.3.0] — 2026-04-21

Big visual + localization release. Five dashboard themes, full English/German
i18n, per-course schedule CRUD, a proper file manager in the Files tab, and a
pile of phone-UX fixes. All backwards compatible — just run the one new
migration on upgrade.

### Added
- **Five dashboard themes.** Pick from **Classic** (the default — serif,
  airy), **Terminal** (mono, teal-on-black, hacker cockpit), **Zine**
  (pastel cream + hand-drawn stickers), **Library** (sepia, card-catalog
  aesthetic), or **Swiss** (12-col grid, red accent). Each one is a full
  reskin — its own sidebar, CSS, and dashboard route, not just a palette.
  Picker lives in **Settings → Theme**.
- **Full in-app i18n — English and German.** Every route, form, toast,
  empty state, error message, and theme-specific prose now runs through
  `i18next`. Language is picked explicitly in **Profile → Language** and
  persists in localStorage, decoupled from the date-format locale.
- **Per-course schedule CRUD.** Add / edit / delete weekly slots from the
  course-detail **Schedule** tab without leaving the page.
- **File manager.** Rename files and folders, recursive folder delete,
  create new folders, and a folder picker on the course form so each
  course scopes its Files tab to a specific prefix in the bucket. New
  backend endpoints `/files/move`, `/files/folder`, and a recursive
  listing helper.
- **Claude Design prompt template** under `docs/claude-design-prompt.md`
  plus four worked-example outputs under `docs/examples/` — the starting
  points for the Terminal / Zine / Library / Swiss themes.

### Changed
- **Phone UX pass.** 16 px form inputs (no more iOS zoom-on-focus), dvh
  for keyboard-aware layout, date-picker chrome contained inside its
  Field on iOS Safari, classic-theme weekly grid now renders the same
  multi-column time grid on phone (with horizontal scroll) instead of a
  stacked list — matches what the themed dashboards do.
- **Course edit affordance** moved from a hover overlay on the course
  card to an explicit **Edit course** button inside the course-detail
  header. Notes and exam editing split out into their own cards with
  their own edit buttons. "Scheduled" field on exams relabeled to
  "Exam date".
- **Dashboard top strip** on phone shows weekday / date / semester /
  week at a glance.
- **Settings pickers** (timezone, date format) auto-save on change; the
  semester-label text field gets an inline Save button while dirty.
  Success toasts are now neutral instead of green.
- **README hero** replaced with a 2×2 still collage of the four paper
  themes plus a looping GIF of Terminal. Mirrored in the German section.

### Upgrade from v0.2.0

```bash
git pull origin main
npx supabase db push   # applies 20260421000001_theme.sql
cd web && pnpm install && pnpm build
```

The migration adds `app_settings.theme` with default `'editorial'`, so
existing rows land on the Classic theme until you pick something else.

[v0.5.0]: https://github.com/openstudy-dev/OpenStudy/releases/tag/v0.5.0
[v0.3.0]: https://github.com/openstudy-dev/OpenStudy/releases/tag/v0.3.0

## [v0.2.0] — 2026-04-20

Rename pass: the project is now English-canonical from the database up through
the MCP tool names. Migrations moved to `supabase/migrations/` so the Supabase
CLI tracks them properly. If you're upgrading an existing deploy, see the
upgrade notes below — pushing `main` won't fix your schema on its own.

### Breaking
- **MCP tools renamed.** `list_klausuren` → `list_exams`, `update_klausur` →
  `update_exam`. `upsert_schedule_slot` → `create_schedule_slot` (signature
  is a pure create now; use `update_schedule_slot` to patch). `now_berlin`
  removed — use `now_here`. Any cached tool lists in Claude.ai / Claude Code
  will need to re-fetch after the push.
- **DB schema.** Table `klausuren` renamed to `exams`. Columns
  `courses.klausur_weight` / `klausur_retries` renamed to `exam_weight` /
  `exam_retries`.
- **Enum values.** Slot / lecture kinds moved from
  `Vorlesung|Übung|Tutorium|Praktikum` to `lecture|exercise|tutorial|lab`.
  Study-topic kinds from `vorlesung|uebung|reading` to
  `lecture|exercise|reading`. Deliverable kinds from
  `abgabe|project|praktikum|block` to `submission|project|lab|block`. Legacy
  German values are still accepted at the API boundary via a Pydantic
  `BeforeValidator` and normalised on the way in — existing MCP integrations
  keep working.
- **Migration location.** `db/migrations/` → `supabase/migrations/` with
  timestamp-based filenames.

### Added
- Single-file README with a same-page `<details name="lang">` language
  toggle — click 🇬🇧 English or 🇩🇪 Deutsch, the other collapses.
- New migration `20260420000001_english_canonical_kinds.sql` that normalises
  existing German values + renames the table/columns on upgrade.
- FastMCP server-level `instructions` — mental model of the domain, enum
  conventions, and orient-before-you-act guidance injected on every
  `initialize`.

### Changed
- Every MCP tool description rewritten with "when to use / when NOT to use"
  disambiguation plus sibling pointers. Goal: Claude picks the right tool
  first try instead of listing + retrying. Tool count down from 46 → 44.
- UI: hardcoded German strings replaced with English (slot-kind selects,
  deliverable-kind selects, sidebar `Klausuren` → `Exams`, /klausuren →
  /exams, etc.). Displayed kind strings pick up a `capitalize` class for
  polish.
- `INSTALL.md` §4 rewritten around `supabase db push` with an upgrade flow
  for existing DBs (`supabase migration repair --status applied …`) and a
  dashboard-SQL-editor fallback.

### Upgrade from v0.1.0

```bash
git pull origin main
npx supabase link --project-ref YOUR-PROJECT-REF
# If you applied 0001–0004 via the SQL editor, mark them applied first:
npx supabase migration repair --status applied 20260101000001 20260115000001 20260201000001 20260301000001
npx supabase db push   # applies the English-canonical migration
```

Then rebuild the frontend (`cd web && pnpm install && pnpm build`) and redeploy.

[v0.2.0]: https://github.com/openstudy-dev/OpenStudy/releases/tag/v0.2.0

## [v0.1.0] — 2026-04-20

First public release. A self-hostable personal study dashboard with an MCP
connector so Claude (claude.ai, iOS, or Claude Code) can read and write your
coursework.

### Added
- Web app: Dashboard, Courses (create / edit / delete with per-course accent
  color), Course detail, Tasks, Deliverables, Files, Klausuren, Activity,
  Settings (profile + semester).
- Streamable HTTP MCP server at `/mcp`, OAuth 2.1-gated. ~45 tools — every UI
  action exposed plus convenience helpers like `get_fall_behind`,
  `mark_studied`, `read_course_file` (renders PDF pages to PNGs for vision).
- Dark visual design — Fraunces serif + Inter Tight + JetBrains Mono, OKLCH
  palette, ink-dot signature motif, 3 px course-accent stripes.
- Empty-by-default schema + a self-healing settings singleton so new deploys
  boot to an onboarding screen rather than a pre-populated dashboard.
- Docs: [INSTALL.md](./INSTALL.md), [CONTRIBUTING.md](./CONTRIBUTING.md),
  [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md), plus templates for a Claude.ai
  Project system prompt and a Claude Design redesign brief (under `docs/`).
- SQL migrations under `supabase/migrations/` — the complete schema, applied
  via `supabase db push` (or pasted into any Postgres SQL editor, in filename
  order).
- Vercel deployment config (`vercel.json`) — one project hosts both the
  static frontend and the Python API functions.

### Known gaps
- Light mode is tokenised but untested.
- No automated test suite yet (manual QA only).
- Slot kinds are German-labeled by default (`Vorlesung`, `Übung`, `Tutorium`,
  `Praktikum`) — not yet user-configurable.
- Postgres driver is Supabase-specific; swapping it out is a fork, not a
  config flag.

PRs on any of the above are welcome — see
[CONTRIBUTING.md](./CONTRIBUTING.md).

[v0.1.0]: https://github.com/openstudy-dev/OpenStudy/releases/tag/v0.1.0
