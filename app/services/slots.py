from typing import Any, Dict, List, Optional
from .. import db
from ..schemas import Slot, SlotCreate, SlotPatch


def _row_to_slot(row: Dict[str, Any]) -> Slot:
    """Coerce uuid column to string before Pydantic validation.

    Postgres returns `id` as a `uuid.UUID` object via psycopg, but the Slot
    schema declares it as `str`. PostgREST used to JSON-serialize uuids; with
    direct DB access we do the conversion ourselves.
    """
    if "id" in row and row["id"] is not None and not isinstance(row["id"], str):
        row = {**row, "id": str(row["id"])}
    return Slot.model_validate(row)


async def list_slots(course_code: Optional[str] = None) -> List[Slot]:
    if course_code:
        rows = await db.fetch(
            "SELECT * FROM schedule_slots WHERE course_code = %s "
            "ORDER BY weekday, start_time",
            course_code,
        )
    else:
        rows = await db.fetch(
            "SELECT * FROM schedule_slots ORDER BY weekday, start_time"
        )
    return [_row_to_slot(r) for r in rows]


async def create_slot(body: SlotCreate) -> Slot:
    data = body.model_dump(mode="json", exclude_none=True)
    cols = list(data.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    row = await db.fetchrow(
        f"INSERT INTO schedule_slots ({', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create slot for {body.course_code}")
    return _row_to_slot(row)


async def update_slot(slot_id: str, patch: SlotPatch) -> Slot:
    data = patch.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    if not data:
        raise ValueError("empty patch")
    cols = list(data.keys())
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE schedule_slots SET {set_clause} WHERE id = %s RETURNING *",
        *[data[c] for c in cols], slot_id,
    )
    if row is None:
        raise ValueError(f"slot {slot_id} not found")
    return _row_to_slot(row)


async def delete_slot(slot_id: str) -> None:
    await db.execute("DELETE FROM schedule_slots WHERE id = %s", slot_id)
