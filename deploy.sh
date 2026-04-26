#!/usr/bin/env bash
# OpenStudy deploy script — runs on the deployment host inside /opt/openstudy.
#
# Usage:
#   ./deploy.sh             # full deploy: build → migrate → roll → health-gate → rollback-on-fail
#   ./deploy.sh --skip-build # skip image rebuild (useful for env-only changes)
#   ./deploy.sh --no-rollback # halt on health failure but don't auto-rollback (debugging)
#   ./deploy.sh --status     # print current image tags + container health and exit
#
# Behaviour:
#   1. Pre-flight: validate compose, check disk space, check .env files exist.
#   2. Build a new openstudy image (unless --skip-build).
#   3. Tag the currently-running image as openstudy:previous (rollback target).
#   4. Apply pending migrations against the live postgres (still running).
#   5. Recreate the openstudy container with the new image.
#   6. Poll http://127.0.0.1:8000/api/health for up to 60s.
#   7. PASS → prune dangling images, log success.
#      FAIL → re-tag :previous as :latest, recreate container, wait for old health.
#
# Logs to /var/log/openstudy-deploy.log (root-owned).

set -euo pipefail

cd "$(dirname "$0")"

# Compose substitution source: only .env.docker (POSTGRES_*). Service-level
# env_file: directives separately inject .env into the openstudy container
# without $-substitution, so APP_PASSWORD_HASH stays intact.
COMPOSE="docker compose --env-file .env.docker"

LOG=/var/log/openstudy-deploy.log
HEALTH_URL=http://127.0.0.1:8000/api/health
HEALTH_TIMEOUT=60   # seconds
HEALTH_INTERVAL=2   # seconds

SKIP_BUILD=0
NO_ROLLBACK=0
SHOW_STATUS=0
for arg in "$@"; do
    case "$arg" in
        --skip-build)  SKIP_BUILD=1 ;;
        --no-rollback) NO_ROLLBACK=1 ;;
        --status)      SHOW_STATUS=1 ;;
        -h|--help)     sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown flag: $arg" >&2; exit 2 ;;
    esac
done

# ── helpers ──────────────────────────────────────────────────────────────────

ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { local m="$*"; echo "[$(ts)] $m" | tee -a "$LOG"; }
err() { local m="$*"; echo "[$(ts)] ERROR: $m" | tee -a "$LOG" >&2; }

current_image_id() {
    $COMPOSE images openstudy --format '{{.ID}}' 2>/dev/null | head -1
}

container_health() {
    docker inspect --format='{{.State.Health.Status}}' openstudy 2>/dev/null || echo "missing"
}

poll_health() {
    local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local body
        body=$(curl -fsS --max-time 3 "$HEALTH_URL" 2>/dev/null) || body=""
        if [ -n "$body" ] && echo "$body" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
            log "health: PASS — $body"
            return 0
        fi
        sleep "$HEALTH_INTERVAL"
    done
    err "health: FAIL — $HEALTH_URL did not return ok=true within ${HEALTH_TIMEOUT}s"
    $COMPOSE logs --tail=40 openstudy | tee -a "$LOG"
    return 1
}

# ── status mode ──────────────────────────────────────────────────────────────

if [ "$SHOW_STATUS" -eq 1 ]; then
    echo "=== compose state ==="
    $COMPOSE ps
    echo
    echo "=== image tags ==="
    docker images openstudy --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}'
    echo
    echo "=== current openstudy health ==="
    container_health
    echo
    echo "=== last 20 lines of $LOG ==="
    tail -n 20 "$LOG" 2>/dev/null || echo "(no log yet)"
    exit 0
fi

# ── pre-flight ───────────────────────────────────────────────────────────────

log "=== deploy starting ==="

[ -f docker-compose.yml ] || { err "docker-compose.yml missing"; exit 1; }
[ -f .env ]               || { err ".env missing — backend secrets file";  exit 1; }
[ -f .env.docker ]        || { err ".env.docker missing — postgres secrets"; exit 1; }
[ -f Dockerfile ]         || { err "Dockerfile missing"; exit 1; }

log "validating docker-compose.yml..."
$COMPOSE config -q || { err "compose validation failed"; exit 1; }

log "checking disk space (need ≥ 1 GB free)..."
free_kb=$(df --output=avail / | tail -1)
if [ "$free_kb" -lt 1048576 ]; then
    err "low disk: only $((free_kb/1024)) MB free on /"
    exit 1
fi

# ── snapshot rollback target ─────────────────────────────────────────────────

PREV_ID=$(current_image_id || true)
if [ -n "${PREV_ID:-}" ]; then
    log "tagging current image $PREV_ID as openstudy:previous (rollback target)"
    docker tag "$PREV_ID" openstudy:previous
else
    log "no previous image — first deploy"
fi

# ── build ────────────────────────────────────────────────────────────────────

if [ "$SKIP_BUILD" -eq 0 ]; then
    log "building openstudy + frontend images..."
    if ! $COMPOSE build 2>&1 | tee -a "$LOG"; then
        err "build failed — aborting before any container changes"
        exit 1
    fi
else
    log "--skip-build: reusing current images"
fi

# ── ensure postgres is up before migrating ───────────────────────────────────

log "ensuring postgres is up..."
$COMPOSE up -d postgres
# wait for healthy
for _ in $(seq 1 30); do
    pg_health=$(docker inspect --format='{{.State.Health.Status}}' openstudy-postgres 2>/dev/null || echo "starting")
    [ "$pg_health" = "healthy" ] && break
    sleep 1
done
[ "$pg_health" = "healthy" ] || { err "postgres did not become healthy"; exit 1; }
log "postgres: healthy"

# ── migrate ──────────────────────────────────────────────────────────────────

log "running migrations..."
if ! $COMPOSE run --rm --no-deps openstudy uv run --no-sync python scripts/run_migrations.py 2>&1 | tee -a "$LOG"; then
    err "migration failed — aborting before swapping containers (postgres untouched if migration ran in transaction)"
    exit 1
fi

# ── roll forward ─────────────────────────────────────────────────────────────

log "starting postgrest + new openstudy + recreating frontend..."
$COMPOSE up -d postgrest openstudy
# Force-recreate frontend so it picks up its newly built image — without
# this, the running frontend container keeps serving the previous build
# even though `compose build` just produced a fresh image.
$COMPOSE up -d --force-recreate frontend

# ── health gate ──────────────────────────────────────────────────────────────

log "polling $HEALTH_URL (timeout ${HEALTH_TIMEOUT}s)..."
if poll_health; then
    log "deploy: SUCCESS"
    if [ -n "${PREV_ID:-}" ] && [ "$PREV_ID" != "$(current_image_id)" ]; then
        log "pruning dangling images..."
        docker image prune -f >> "$LOG" 2>&1
    fi
    exit 0
fi

# ── rollback ─────────────────────────────────────────────────────────────────

if [ "$NO_ROLLBACK" -eq 1 ]; then
    err "deploy: FAILED — health gate did not pass. --no-rollback set, leaving broken state for inspection"
    exit 1
fi

if [ -z "${PREV_ID:-}" ]; then
    err "deploy: FAILED — no previous image to roll back to (first-ever deploy?)"
    exit 1
fi

log "ROLLBACK: re-tagging openstudy:previous as openstudy:latest..."
docker tag openstudy:previous openstudy:latest
log "ROLLBACK: recreating openstudy container..."
$COMPOSE up -d --force-recreate openstudy

log "ROLLBACK: polling health on restored image..."
if poll_health; then
    err "deploy: FAILED but rollback succeeded — service is on previous image. Investigate and try again."
    exit 1
else
    err "deploy: CATASTROPHIC — rollback also failed health. Service is down. Investigate immediately."
    exit 2
fi
