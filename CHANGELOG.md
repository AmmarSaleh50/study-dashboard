# Changelog

All notable changes to study-dashboard will be documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [SemVer](https://semver.org/spec/v2.0.0.html).

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
- Empty-by-default seed + a settings singleton so new deploys boot with an
  onboarding screen rather than a pre-populated dashboard.
- Docs: [INSTALL.md](./INSTALL.md), [CONTRIBUTING.md](./CONTRIBUTING.md),
  [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md), plus templates for a Claude.ai
  Project system prompt and a Claude Design redesign brief (under `docs/`).
- Four SQL migrations under `db/migrations/` — the complete schema, apply in
  numeric order to any Postgres.
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
