from typing import List
from uuid import UUID
from .. import db
from ..schemas import Course, CourseCreate, CoursePatch
from ._helpers import validated_cols


async def list_courses(user_id: UUID) -> List[Course]:
    rows = await db.fetch(
        "SELECT * FROM courses WHERE user_id = %s ORDER BY code",
        user_id,
    )
    return [Course.model_validate(r) for r in rows]


async def get_course(user_id: UUID, code: str) -> Course | None:
    row = await db.fetchrow(
        "SELECT * FROM courses WHERE user_id = %s AND code = %s LIMIT 1",
        user_id, code,
    )
    return Course.model_validate(row) if row else None


async def create_course(user_id: UUID, body: CourseCreate) -> Course:
    data = body.model_dump(mode="json", exclude_none=True)
    cols = validated_cols(CourseCreate, data)
    placeholders = ", ".join(["%s"] * (len(cols) + 1))
    row = await db.fetchrow(
        f"INSERT INTO courses (user_id, {', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        user_id, *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create course {body.code}")
    return Course.model_validate(row)


async def update_course(user_id: UUID, code: str, patch: CoursePatch) -> Course:
    data = patch.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    if not data:
        course = await get_course(user_id, code)
        if not course:
            raise ValueError(f"course {code} not found")
        return course
    cols = validated_cols(CoursePatch, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE courses SET {set_clause} WHERE user_id = %s AND code = %s RETURNING *",
        *[data[c] for c in cols], user_id, code,
    )
    if row is None:
        raise ValueError(f"course {code} not found")
    return Course.model_validate(row)


async def delete_course(user_id: UUID, code: str) -> None:
    await db.execute(
        "DELETE FROM courses WHERE user_id = %s AND code = %s",
        user_id, code,
    )
