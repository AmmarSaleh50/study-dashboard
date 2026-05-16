# Row Level Security (Phase 4)

Phase 4 added per-user RLS policies on every owned table. They reference
the session GUC `app.user_id`, which the app sets via the auth middleware
on every authenticated request.

## Current state

- The app connects as a superuser-equivalent role that has BYPASSRLS.
- Policies are inert.
- App-side `WHERE user_id = $1` filters (Phase 2) are the only enforcement today.

## Switching to enforce RLS in prod

### 1. Create a non-bypass role

```sql
CREATE ROLE openstudy_app NOBYPASSRLS LOGIN PASSWORD '<strong-password>';
GRANT USAGE ON SCHEMA public TO openstudy_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO openstudy_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO openstudy_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO openstudy_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO openstudy_app;
```

### 2. Update `.env.docker`

```
DATABASE_URL=postgresql://openstudy_app:<strong-password>@postgres:5432/openstudy
```

### 3. Known limitation — signup / email-lookup paths

Some operations (signup needs to look up users by email without RLS
limiting to self) need either a separate privileged connection or a
`SECURITY DEFINER` function. Phase 4 leaves this as a future operational
decision — the superuser bypass role keeps things working unchanged until
that decision is made.

### 4. Verify post-switch

```bash
curl https://openstudy.dev/api/health        # {"ok":true,...}
curl -H "Cookie: <session>" https://openstudy.dev/api/courses  # operator's courses only
# Sign up a second user; verify that user's data is isolated from the first.
```

### 5. Rollback

Revert `DATABASE_URL` in `.env.docker` to the superuser connection string,
then restart the backend:

```bash
cd /opt/openstudy && docker compose --env-file .env.docker up -d --force-recreate openstudy
```

RLS becomes inert again; `WHERE user_id = $1` service-layer filters remain active.
