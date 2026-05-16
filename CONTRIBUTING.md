# Contributing

Thanks for considering a contribution — genuinely. Whether it's a one-line typo fix, a new MCP tool, or just an issue saying "this didn't work on my machine, here's what I saw" — all of it helps.

This file just has a couple of notes so you know what to expect and we can keep the back-and-forth short.

## Glossary

Two related but distinct identities show up across the codebase. Phase 0
makes the distinction explicit so the multi-tenant migration in later
phases is easier to reason about.

- **Operator** — server administrator who runs `./deploy.sh`, has SSH
  access to the deploy box, and sets env vars like `OPERATOR_EMAIL`,
  `SECRETS_ENCRYPTION_KEY`, and the like. Always exactly one per
  deployment.
- **User** — a row in the `users` table (added in Phase 1 of the
  multi-tenant migration). Created via `/auth/signup` (post-Phase 3) or
  by the operator via CLI. Many users per deployment.

Pre-multi-tenant (≤ v0.6) the operator and user are the same person.
Post v0.7, they diverge: the operator administers the server; users sign
up and use the product. Auth code paths use `User` (a dataclass in
`app/auth.py`) to carry the user identity through requests.

## What's in scope

Basically anything that makes the app better for someone self-hosting it. A non-exhaustive list of things I'd love help with:

- **Bug fixes** — obvious one. If you hit a bug, please file an issue even if you can't fix it yourself.
- **Self-host polish** — clearer docs, better error messages when an env var is missing, packaging niceties (a Helm chart, a one-click deploy button for popular PaaS, a `compose.override.yml` template for common variations).
- **Accessibility + keyboard shortcuts** — the UI is dark, dense, and keyboard-navigable-ish, but could be better.
- **i18n / localization** — the Slot `kind` labels are German (`Vorlesung`, `Übung`) by default. Making those user-configurable or translatable would help non-EU users a lot.
- **New MCP tools** — if you find yourself wishing Claude could do `X` and there's a natural way to expose it, just add it. Pattern is in `app/mcp_tools.py`.
- **Performance / bundle size** — the frontend chunk is bigger than it needs to be; someone who knows their way around Vite code-splitting could shave a lot.
- **Tests** — there's no suite yet. Adding pytest + Vitest scaffolding is its own welcome PR.

## Things worth a quick issue first

Not "no" — just "let's talk first so you don't waste a weekend":

- Major framework swaps (React → Svelte, FastAPI → Django).
- Replacing the `psycopg` async pool with a different DB driver (SQLAlchemy, asyncpg, etc.) — the pool is small but it's load-bearing; every service file goes through it.
- New top-level entities beyond the current data model (Course / Schedule slot / Lecture / Study topic / Deliverable / Task / Klausur).
- Multi-user / team / sharing features — the single-user-per-deploy assumption is load-bearing in a bunch of places, and shifting it is a big project.

A one-liner issue like *"would you take a PR that X?"* is all it takes.

## Dev setup

See [INSTALL.md](./INSTALL.md) for the full walkthrough. TL;DR:

```bash
cp .env.example .env                 # fill APP_PASSWORD_HASH, SESSION_SECRET
cat > .env.docker <<EOF              # Postgres credentials
POSTGRES_USER=openstudy
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=openstudy
EOF
./deploy.sh                          # builds + brings up postgres + openstudy

cd web && pnpm install && pnpm dev
```

## Code conventions

- **Python:** `ruff` is configured in `pyproject.toml` (line-length 100, py312 target). Run `uv run ruff check .` and `uv run ruff format .` before pushing.
- **TypeScript/React:** `eslint` is configured in `web/`. Run `pnpm lint` from `web/`. Components are function components + hooks; state via React Query for server state and `useState`/`useReducer` for local.
- **Commit messages:** short imperative subject line (≤70 chars), optional body explaining the *why*. See `git log` for the house style.
- **Scope per PR:** one logical change. A bug fix + a refactor + a new feature should be three PRs.

## The fall-behind mirror

`app/services/fall_behind.py` (Python, runs on the server / in MCP) and `web/src/lib/fall-behind.ts` (TypeScript, runs in the browser) are **intentional mirrors**. Any change to the rules — severity thresholds, grace periods, which topics count — must be applied to both. PRs that only touch one side will get a request for the other.

## Testing

The backend has a pytest suite (213 tests as of v0.6.0) that runs against a real Postgres testcontainer with per-test transaction rollback — every test gets a clean DB state without paying for container churn. Service-layer, MCP-tool, and end-to-end OAuth/login flows are all covered.

```bash
uv run --no-sync pytest -q              # full suite
uv run --no-sync pytest tests/mcp -x    # just the MCP tool tests
```

The frontend has no automated tests yet. For frontend changes, run `pnpm build` to make sure TypeScript is still happy, then manually click through the affected views in `pnpm dev`.

For MCP tool changes specifically: write a happy-path test in `tests/mcp/test_<entity>.py` matching the existing pattern (it's just `await get_tool_fn(server, "tool_name")(**kwargs)`), then `./deploy.sh` and exercise it from Claude Code (`claude mcp add --transport http openstudy-local http://localhost:8000/mcp`) to confirm the wire-level call works too.

A frontend Vitest suite is still on the wishlist — PRs welcome.

## Submitting a PR

1. Fork, branch, commit.
2. Run the relevant linter/build (`ruff`, `pnpm lint`, `pnpm build`).
3. Push and open a PR against `main`.
4. In the PR description, include: what the change does, how you tested it, anything reviewers should pay attention to.
5. Be patient — this is a side project. Responses may take a few days.

## Self-host rebranding

If you're running a public deploy of this code, the frontend reads `VITE_SITE_URL` and `VITE_SITE_NAME` from the environment so you can set your own domain + display name without code edits — `scripts/build-seo.mjs` regenerates `robots.txt`, `sitemap.xml`, and `manifest.webmanifest` from those vars at build time. The brand assets under `web/public/brand/` are also a single drop-in path if you want to swap the wordmark for your own.

PRs that improve the `VITE_SITE_*` plumbing or make rebranding easier are welcome.

## License

By submitting a PR you agree that your contribution is licensed under the same MIT license as the rest of the project (see [LICENSE](./LICENSE)).
