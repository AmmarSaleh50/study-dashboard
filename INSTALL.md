# Install OpenStudy

End-to-end self-hosting guide. The whole stack — Postgres, the
FastAPI backend, the static frontend, and a reverse proxy with TLS — runs
on a single Docker host. Anything that runs Docker works: a small VPS, a
home server, a spare laptop.

If you only want a high-level pitch, see [README.md](./README.md). This file
is the operational walkthrough.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the repo](#2-clone-the-repo)
3. [Generate secrets and write the env files](#3-generate-secrets-and-write-the-env-files)
4. [Bring up the stack](#4-bring-up-the-stack)
5. [Build and serve the frontend](#5-build-and-serve-the-frontend)
6. [Put it on a public domain (optional, required for hosted Claude clients)](#6-put-it-on-a-public-domain)
7. [Connect an MCP client](#7-connect-an-mcp-client)
8. [Day-2 operations](#8-day-2-operations)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

On the box that will run the stack:

- **Docker** ≥ 24 with **Compose v2.30+** (we rely on the `format: raw` env-file flag)
- **Bash** + standard GNU tools (`openssl`, `curl`, `sed`, `grep`)

On a workstation (which can be the same box) for building the frontend:

- **Node 20+** + **pnpm** (`corepack enable && corepack prepare pnpm@latest --activate`)

That's it. No Python on the host — the backend builds inside Docker.

---

## 2. Clone the repo

```bash
git clone https://github.com/openstudy-dev/OpenStudy /opt/openstudy
cd /opt/openstudy
```

`/opt/openstudy` is the conventional install path used in the rest of this
guide. Anywhere else works; just adjust the paths below.

---

## 3. Generate secrets and write the env files

OpenStudy reads two env files, both kept out of git:

- **`.env`** — application secrets used by the FastAPI container
  (login password hash, session secret, optional integrations).
- **`.env.docker`** — Postgres credentials only, used to spin up the
  database container.

Create them:

```bash
# .env — copy the template, then fill in the placeholders
cp .env.example .env

# Argon2id-hash a login password you'll use to sign in
docker run --rm python:3.12-slim sh -c \
  'pip install -q argon2-cffi && python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash(input(\"password: \")))"'
# → paste the resulting hash as APP_PASSWORD_HASH in .env

# Generate a session-cookie signing secret
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
# → paste as SESSION_SECRET in .env

# Generate a strong Postgres password and write the docker-only env file
cat > .env.docker <<EOF
POSTGRES_USER=openstudy
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=openstudy
EOF
chmod 600 .env .env.docker
```

The other variables in `.env` are optional and document themselves —
the internal API secret used by webhooks, the public URL the app
advertises in OAuth flows. Telegram credentials are configured per-user
via **Settings → Telegram** after first login (no env vars needed).

---

## 4. Bring up the stack

```bash
./deploy.sh
```

`deploy.sh` does, in order:

1. Pre-flight (compose validation, disk space, env-file presence).
2. Tags the currently running image as `openstudy:previous` so it can roll back.
3. Builds a fresh `openstudy:latest` image from the `Dockerfile`.
4. Starts the Postgres container, waits for `pg_isready`.
5. Runs `scripts/run_migrations.py` against Postgres (idempotent — re-applies
   nothing that's already been recorded in the `_migrations` table).
6. Starts the openstudy container.
7. Polls `GET http://127.0.0.1:8000/api/health` for up to 60 s.
8. **Pass:** prunes dangling images, exits 0.
   **Fail:** re-tags `:previous` as `:latest`, recreates the container, waits
   for the previous build's health to come back, exits non-zero.

Verify:

```bash
curl http://127.0.0.1:8000/api/health
# → {"ok":true,"version":"...","db":"ok","storage":"ok ..."}
```

You should also see the running containers (`openstudy`, `openstudy-postgres`,
`openstudy-frontend`) when you run `./deploy.sh --status`.

### First-time operator login

After running `./deploy.sh`:

1. Set `APP_PASSWORD_HASH` in `.env.docker` to your argon2id-hashed password
   (use `uv run python -m app.tools.hashpw 'your-password'` to generate).
2. Set `OPERATOR_EMAIL` to your email (or leave the default `operator@local`).
3. Run `./deploy.sh` — it invokes `scripts/seed_operator_password.py` which
   sets `users.password_hash` for the operator user from your env var.
4. Log in at `https://your-domain/login` with `OPERATOR_EMAIL` + your password.
5. Configure your Telegram bot in **Settings → Telegram** (per-user; no env
   vars needed).

`APP_PASSWORD_HASH` is bootstrap-only — the seed script reads it once at
deploy time. Subsequent logins authenticate against `users.password_hash`
in the database.

### Restoring data into a fresh box

If you're moving from another deployment (or restoring a backup), apply
your data dump after step 5 but before bringing up the openstudy container:

```bash
docker compose --env-file .env.docker up -d postgres
docker compose --env-file .env.docker run --rm --no-deps openstudy \
  uv run --no-sync python scripts/run_migrations.py
docker exec -i openstudy-postgres psql -U openstudy -d openstudy < your-data.sql
./deploy.sh --skip-build   # then continue with the normal deploy
```

---

## 5. Build and serve the frontend

The frontend builds and runs as a container too — `./deploy.sh` already
brought it up alongside the backend. It listens on `127.0.0.1:8080` and
internally proxies API traffic to the openstudy container, so the rest
of your stack only needs to talk to one port.

To customise the build (your domain in canonical/OG tags, your site
name in the manifest), set these in `.env.docker` before deploying:

```
PUBLIC_SITE_URL=https://your-domain.tld
PUBLIC_SITE_NAME=Your Name
PUBLIC_SHOW_LANDING=false
```

Then `./deploy.sh` rebuilds the frontend image with your values baked in.

**For local frontend development** (Vite hot-reload, faster iteration):

```bash
cd web
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
pnpm install
pnpm dev    # → http://localhost:5173, hot-reloads against the dockerised backend
```

---

## 6. Put it on a public domain

Required if you want Claude.ai or the Claude iOS app to reach the MCP
endpoint. Skip for Claude-Code-only setups (`http://localhost:8080/mcp`
works fine).

The example below uses **Caddy** because it's two lines for automatic TLS
via Let's Encrypt. Nginx + Certbot, Traefik, anything else works the same way.

`/etc/caddy/Caddyfile`:

```
your-domain.tld {
    encode gzip
    reverse_proxy 127.0.0.1:8080 {
        flush_interval -1   # required for /mcp Streamable HTTP
    }
}
```

That's it. The host's outer Caddy terminates TLS and hands everything off
to the frontend container, which then routes static assets locally and
backend traffic to the openstudy service on the internal docker network.

Reload Caddy: `sudo systemctl reload caddy`. Visit `https://your-domain.tld`
— TLS gets provisioned automatically on the first hit.

---

## 7. Connect an MCP client

The MCP endpoint is at `/mcp`, OAuth 2.1-protected. The same URL works
across every Claude surface.

### Claude.ai (browser + iOS)

Settings → Connectors → **Add custom connector** → paste
`https://your-domain.tld/mcp` → complete the OAuth consent in the popup.

### Claude Code (local CLI)

```bash
claude mcp add --transport http --scope user \
  openstudy https://your-domain.tld/mcp
```

For development:

```bash
claude mcp add --transport http --scope user \
  openstudy-local http://localhost:8000/mcp
```

### Verify it works

From a Claude session: *"list my courses"*. The agent should call
`mcp__openstudy__list_courses` and respond with whatever you've created.

---

## 8. Day-2 operations

### Deploying a change

```bash
git pull
./deploy.sh
```

That's it — the script handles build, migrate, health-check, and rollback.

If you only changed env vars (no code), use `--skip-build`:

```bash
./deploy.sh --skip-build
```

### Backups

A daily systemd timer (or any cron equivalent) should:

- `rsync /opt/courses/ → /opt/backup/<date>/courses/`
- `docker exec openstudy-postgres pg_dump -U openstudy openstudy | gzip > /opt/backup/<date>/postgres.sql.gz`
- Push `/opt/backup/` somewhere off-host (S3, Backblaze, your NAS) — the
  whole point of a backup is surviving the box dying.

### Migrations

Add a new SQL file under `migrations/` with a timestamp greater than
`00000000000000_baseline.sql`:

```bash
fn="migrations/$(date -u +%Y%m%d%H%M%S)_my_change.sql"
cat > "$fn" <<'SQL'
-- Describe the change
alter table courses add column if not exists tagline text;
SQL
```

Then `./deploy.sh` — the migration runs in a transaction, gets recorded
in `_migrations` with its sha256, and any future re-run is a no-op.
Files are immutable once recorded; if you need to amend, write a new
migration.

### Rolling back

Routine rollback happens automatically when health fails. To roll back
manually after a successful but unwanted deploy:

```bash
docker tag openstudy:previous openstudy:latest
docker compose --env-file .env.docker up -d --force-recreate openstudy
```

### Updating the docker images

```bash
docker compose --env-file .env.docker pull   # postgres
./deploy.sh                                   # rebuilds openstudy
```

---

## 9. Troubleshooting

**`./deploy.sh` says "compose validation failed".**
Run `docker compose --env-file .env.docker config` to see the error. Most
common cause: `.env.docker` missing a key, or compose version below 2.30.

**`/api/health` returns `{"ok": false, "db": "error: ..."}`.**
The FastAPI container can't reach Postgres. Check `docker logs openstudy-postgres`
for boot errors; verify the values in `.env.docker` match what's in
`/opt/postgres-data/` (the directory persists between runs — if you
changed the password after first boot, Postgres is still using the old one).

**`/api/health` returns `{"ok": false, "storage": "error: ..."}`.**
The bind-mount for `/opt/courses` failed. Check the path exists on the host
and is readable by the container. `docker exec openstudy ls /opt/courses`
should show your course tree.

**Login returns 401 with the right password.**
Re-hash the password, update `APP_PASSWORD_HASH` in `.env.docker`, then
run `./deploy.sh` so `scripts/seed_operator_password.py` writes the new
hash into `users.password_hash`. Common gotcha: the hash starts with
`$argon2id$…` — those `$` characters are literal, not env interpolation.
The compose `env_file: format: raw` directive prevents mangling, but if
you've manually exported the variable in a shell, the `$` chars need to
be single-quoted.

**MCP returns 401 from a Claude client.**
The OAuth token cached by the client expired or was revoked. Reconnect:
in claude.ai disconnect and re-add the connector; in Claude Code run
`/mcp` and re-authenticate openstudy.
