from typing import List
from uuid import UUID

from .. import db
from ..schemas import Exam, ExamPatch
from ._helpers import model_dump_clean, validated_cols


async def list_exams(user_id: UUID) -> List[Exam]:
    rows = await db.fetch(
        "SELECT * FROM exams WHERE user_id = %s ORDER BY course_code",
        user_id,
    )
    return [Exam.model_validate(r) for r in rows]


async def get_exam(user_id: UUID, course_code: str) -> Exam | None:
    row = await db.fetchrow(
        "SELECT * FROM exams WHERE user_id = %s AND course_code = %s LIMIT 1",
        user_id, course_code,
    )
    return Exam.model_validate(row) if row else None


async def update_exam(user_id: UUID, course_code: str, patch: ExamPatch) -> Exam:
    """Per-course singleton upsert: insert if missing, update if present.

    The composite PK (user_id, course_code) routes the upsert in a single
    round-trip via ON CONFLICT. An empty patch on an existing row is a no-op
    (returns the row unchanged); on a missing row it inserts a defaults-only row.
    """
    data = model_dump_clean(patch)

    if not data:
        # Empty patch: return existing row, or insert a defaults-only row.
        existing = await get_exam(user_id, course_code)
        if existing is not None:
            return existing
        row = await db.fetchrow(
            "INSERT INTO exams (user_id, course_code) VALUES (%s, %s) RETURNING *",
            user_id, course_code,
        )
        if row is None:
            raise ValueError(f"failed to upsert exam for {course_code}")
        return Exam.model_validate(row)

    cols = validated_cols(ExamPatch, data)
    insert_cols = ["user_id", "course_code", *cols]
    insert_placeholders = ", ".join(["%s"] * len(insert_cols))
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    sql = (
        f"INSERT INTO exams ({', '.join(insert_cols)}) "
        f"VALUES ({insert_placeholders}) "
        f"ON CONFLICT (user_id, course_code) DO UPDATE SET {update_set} "
        f"RETURNING *"
    )
    row = await db.fetchrow(sql, user_id, course_code, *[data[c] for c in cols])
    if row is None:
        raise ValueError(f"failed to upsert exam for {course_code}")
    return Exam.model_validate(row)


__all__ = ["list_exams", "get_exam", "update_exam"]
