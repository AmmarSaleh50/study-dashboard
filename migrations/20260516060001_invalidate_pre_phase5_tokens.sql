-- Phase 5: invalidate all pre-Phase-5 tokens. They predate user_id binding;
-- force fresh consent so every active token has a real user_id.

BEGIN;

-- revoked column already exists (baseline). Just bulk-revoke every token
-- issued before the Phase-5 consent flow was in place.
UPDATE public.oauth_tokens SET revoked = true WHERE revoked = false;

COMMIT;
