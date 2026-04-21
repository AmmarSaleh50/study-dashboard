# Changelog

All notable changes to study-dashboard will be documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [SemVer](https://semver.org/spec/v2.0.0.html).

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

[v0.3.0]: https://github.com/AmmarSaleh50/study-dashboard/releases/tag/v0.3.0

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

[v0.2.0]: https://github.com/AmmarSaleh50/study-dashboard/releases/tag/v0.2.0

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

[v0.1.0]: https://github.com/AmmarSaleh50/study-dashboard/releases/tag/v0.1.0
