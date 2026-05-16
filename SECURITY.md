# Security Policy

## Supported Versions

| Version | Status |
|---------|--------|
| 0.7.x   | ✅ Supported — security fixes |
| < 0.7   | ❌ Unsupported — please upgrade |

## Reporting a Vulnerability

If you discover a security issue, please **do not** open a public GitHub
issue. Instead, email:

**security@openstudy.dev** (forwarded to the maintainer)

You can also report via GitHub's private vulnerability disclosure:
**[Report a vulnerability](https://github.com/openstudy-dev/OpenStudy/security/advisories/new)**

### What to include

- A description of the vulnerability and its potential impact.
- Steps to reproduce (PoC if possible — without harming other users).
- Affected version(s).
- Your preferred contact info if you want credit / coordination.

### What to expect

- Acknowledgement within **72 hours**.
- An initial assessment within **7 days**.
- A fix or disclosure timeline within **30 days** for high-severity issues.
- Public disclosure happens **after** a fix ships, or **90 days** after
  the initial report — whichever comes first.

## Scope

OpenStudy is multi-tenant. The following are in scope for security
reports:

- **Cross-user data exposure** — one user reading/writing another user's
  data via any API surface (REST, MCP, file storage).
- **Authentication / session bypass** — login, signup, password reset,
  email verification, TOTP, OAuth consent.
- **Privilege escalation** — non-operator user gaining operator
  capabilities.
- **Credential leakage** — Telegram tokens, encrypted secrets, session
  cookies.
- **Stored XSS / SQL injection** — anywhere user input flows into a
  query or rendered HTML.

Out of scope:
- Bugs in third-party services (Hetzner, Cloudflare, Telegram).
- Denial-of-service via expected rate limits.
- Self-XSS / social engineering of the operator.
- Issues in self-hosted setups due to operator misconfiguration
  (weak passwords, exposed env files, etc.).
