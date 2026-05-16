"""Phase 1 schema invariants.

Locks the multi-tenant integrity guarantees in place after Phase 1's
schema migrations:
- Deleting a user cascades to all owned data.
- Composite FKs make cross-user references structurally impossible.
- The operator seed row exists after migrations.
- Two users can have the same course code (composite PK on (user_id, code)).
"""
from datetime import datetime, timezone, date
from uuid import UUID, uuid4

import pytest

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_operator_user_seed_row_exists(client, db_conn):
    """Migration 020001 must seed the operator user."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, email, display_name FROM users WHERE id = %s",
            (OPERATOR,),
        )
        row = await cur.fetchone()
        assert row is not None
        assert row["email"] == "operator@local"
        assert row["display_name"] == "Operator"


@pytest.mark.asyncio
async def test_delete_user_cascades_to_owned_data(client, db_conn):
    """Inserting a second user + course, then deleting the user, removes the course.

    events.user_id has no FK (dropped in migration 20260516020008) so the audit
    trigger can insert freely during the cascade without a constraint violation.
    """
    new_user = str(uuid4())
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s)",
            (new_user, f"user-{new_user}@test", "Test User"),
        )
        # Insert a course manually pinning user_id.
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
            (new_user, "CASCU", "Cascade User Test"),
        )
        await cur.execute(
            "SELECT count(*) AS c FROM courses WHERE user_id = %s", (new_user,)
        )
        assert (await cur.fetchone())["c"] == 1

        # Delete the user — should cascade to courses.
        await cur.execute("DELETE FROM users WHERE id = %s", (new_user,))

        # The user's courses must be gone (CASCADE on users(id)).
        await cur.execute(
            "SELECT count(*) AS c FROM courses WHERE user_id = %s", (new_user,)
        )
        assert (await cur.fetchone())["c"] == 0


@pytest.mark.asyncio
async def test_two_users_can_have_same_course_code(client, db_conn):
    """Composite PK on (user_id, code) means course codes are per-user.

    Two distinct users should be able to both have a 'MATH' course.
    """
    second_user = str(uuid4())
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s)",
            (second_user, f"u-{second_user}@test", "Second"),
        )
        # Operator gets a MATH course.
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
            (str(OPERATOR), "MATHX", "Operator's math"),
        )
        # Second user gets their own MATH course (same code, different user).
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
            (second_user, "MATHX", "Second user's math"),
        )
        await cur.execute(
            "SELECT count(*) AS c FROM courses WHERE code = 'MATHX'"
        )
        assert (await cur.fetchone())["c"] == 2


@pytest.mark.asyncio
async def test_composite_fk_blocks_cross_user_references(client, db_conn):
    """Inserting a study_topic with user_id=A but course belonging to user B must fail.

    The composite FK (user_id, course_code) → courses(user_id, code) enforces
    this at the schema layer: there is no way for user A to attach a study
    topic to user B's course.
    """
    import psycopg
    second_user = str(uuid4())
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s)",
            (second_user, f"u2-{second_user}@test", "Second"),
        )
        # Operator owns CRSXR.
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
            (str(OPERATOR), "CRSXR", "Cross-ref test"),
        )
        # Attempting to insert a study_topic as the second user pointing at
        # operator's course must raise ForeignKeyViolation.
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await cur.execute(
                "INSERT INTO study_topics (user_id, course_code, name, kind) "
                "VALUES (%s, %s, %s, %s)",
                (second_user, "CRSXR", "stolen topic", "lecture"),
            )
