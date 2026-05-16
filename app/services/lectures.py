from typing import List, Optional
from uuid import UUID

from .. import db
from ..schemas import Lecture, LectureCreate, LecturePatch
from ._helpers import validated_cols


async def list_lectures(user_id: UUID, course_code: Optional[str] = None) -> List[Lecture]:
    if course_code:
        rows = await db.fetch(
            "SELECT * FROM lectures WHERE user_id = %s AND course_code = %s "
            "ORDER BY course_code, number",
            user_id, course_code,
        )
    else:
        rows = await db.fetch(
            "SELECT * FROM lectures WHERE user_id = %s ORDER BY course_code, number",
            user_id,
        )
    return [Lecture.model_validate(r) for r in rows]


async def get_lecture(user_id: UUID, lecture_id: str) -> Optional[Lecture]:
    row = await db.fetchrow(
        "SELECT * FROM lectures WHERE user_id = %s AND id = %s LIMIT 1",
        user_id, lecture_id,
    )
    return Lecture.model_validate(row) if row else None


async def create_lecture(user_id: UUID, payload: LectureCreate) -> Lecture:
    data = payload.model_dump(mode="json", exclude_none=True)
    cols = validated_cols(LectureCreate, data)
    placeholders = ", ".join(["%s"] * (len(cols) + 1))
    row = await db.fetchrow(
        f"INSERT INTO lectures (user_id, {', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        user_id, *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create lecture for {payload.course_code}")
    return Lecture.model_validate(row)


async def update_lecture(user_id: UUID, lecture_id: str, patch: LecturePatch) -> Lecture:
    data = patch.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    if not data:
        raise ValueError("empty patch")
    cols = validated_cols(LecturePatch, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE lectures SET {set_clause} WHERE user_id = %s AND id = %s RETURNING *",
        *[data[c] for c in cols], user_id, lecture_id,
    )
    if row is None:
        raise ValueError(f"lecture {lecture_id} not found")
    return Lecture.model_validate(row)


async def mark_attended(user_id: UUID, lecture_id: str, attended: bool = True) -> Lecture:
    return await update_lecture(user_id, lecture_id, LecturePatch(attended=attended))


async def delete_lecture(user_id: UUID, lecture_id: str) -> None:
    await db.execute(
        "DELETE FROM lectures WHERE user_id = %s AND id = %s",
        user_id, lecture_id,
    )
