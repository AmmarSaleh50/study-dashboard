from typing import List, Optional
from uuid import UUID
from .. import db
from ..schemas import Slot, SlotCreate, SlotPatch
from ._helpers import validated_cols


async def list_slots(user_id: UUID, course_code: Optional[str] = None) -> List[Slot]:
    if course_code:
        rows = await db.fetch(
            "SELECT * FROM schedule_slots WHERE user_id = %s AND course_code = %s "
            "ORDER BY weekday, start_time",
            user_id, course_code,
        )
    else:
        rows = await db.fetch(
            "SELECT * FROM schedule_slots WHERE user_id = %s ORDER BY weekday, start_time",
            user_id,
        )
    return [Slot.model_validate(r) for r in rows]


async def create_slot(user_id: UUID, body: SlotCreate) -> Slot:
    data = body.model_dump(mode="json", exclude_none=True)
    cols = validated_cols(SlotCreate, data)
    placeholders = ", ".join(["%s"] * (len(cols) + 1))
    row = await db.fetchrow(
        f"INSERT INTO schedule_slots (user_id, {', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        user_id, *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create slot for {body.course_code}")
    return Slot.model_validate(row)


async def update_slot(user_id: UUID, slot_id: str, patch: SlotPatch) -> Slot:
    data = patch.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    if not data:
        raise ValueError("empty patch")
    cols = validated_cols(SlotPatch, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE schedule_slots SET {set_clause} WHERE user_id = %s AND id = %s RETURNING *",
        *[data[c] for c in cols], user_id, slot_id,
    )
    if row is None:
        raise ValueError(f"slot {slot_id} not found")
    return Slot.model_validate(row)


async def delete_slot(user_id: UUID, slot_id: str) -> None:
    await db.execute(
        "DELETE FROM schedule_slots WHERE user_id = %s AND id = %s",
        user_id, slot_id,
    )
