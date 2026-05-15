"""Smoke test for app/intents/tasks.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_tasks_intent_create_complete_reopen(client, db_conn):
    from app.intents import tasks as intent
    from app.schemas import TaskCreate

    task = await intent.create_task(OPERATOR, TaskCreate(title="Intent task"))
    assert task.title == "Intent task"
    assert task.status == "open"

    done = await intent.complete_task(OPERATOR, str(task.id))
    assert done.status == "done"

    reopened = await intent.reopen_task(OPERATOR, str(task.id))
    assert reopened.status == "open"


@pytest.mark.asyncio
async def test_tasks_intent_list(client, db_conn):
    from app.intents import tasks as intent
    from app.schemas import TaskCreate

    await intent.create_task(OPERATOR, TaskCreate(title="Listed task"))
    lst = await intent.list_tasks(OPERATOR)
    assert any(t.title == "Listed task" for t in lst)
