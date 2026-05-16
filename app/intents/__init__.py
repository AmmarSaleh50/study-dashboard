"""Intents package — user-scoped entry points for REST and MCP callers.

Pass-throughs to app.services.*. The user_id parameter is forwarded to
each service, which filters by it via WHERE user_id = $1.
"""
