from typing import List

from .. import db
from ..schemas import Exam, ExamPatch
from ._helpers import model_dump_clean, validated_cols


async def list_exams() -> List[Exam]:
    rows = await db.fetch("SELECT * FROM exams ORDER BY course_code")
    return [Exam.model_validate(r) for r in rows]


async def get_exam(course_code: str) -> Exam | None:
    row = await db.fetchrow(
        "SELECT * FROM exams WHERE course_code = %s LIMIT 1",
        course_code,
    )
    return Exam.model_validate(row) if row else None


async def update_exam(course_code: str, patch: ExamPatch) -> Exam:
    """Per-course singleton upsert: insert if missing, update if present.

    `course_code` is the primary key on `exams`, so ON CONFLICT (course_code)
    routes the upsert in a single round-trip. An empty patch on an existing
    row is a no-op (returns the row unchanged); on a missing row it inserts
    a default exam keyed by course_code.
    """
    data = model_dump_clean(patch)

    if not data:
        # Empty patch: return existing row, or insert a defaults-only row.
        existing = await get_exam(course_code)
        if existing is not None:
            return existing
        row = await db.fetchrow(
            "INSERT INTO exams (course_code) VALUES (%s) RETURNING *",
            course_code,
        )
        if row is None:
            raise ValueError(f"failed to upsert exam for {course_code}")
        return Exam.model_validate(row)

    cols = validated_cols(ExamPatch, data)
    insert_cols = ["course_code", *cols]
    insert_placeholders = ", ".join(["%s"] * len(insert_cols))
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    sql = (
        f"INSERT INTO exams ({', '.join(insert_cols)}) "
        f"VALUES ({insert_placeholders}) "
        f"ON CONFLICT (course_code) DO UPDATE SET {update_set} "
        f"RETURNING *"
    )
    row = await db.fetchrow(sql, course_code, *[data[c] for c in cols])
    if row is None:
        raise ValueError(f"failed to upsert exam for {course_code}")
    return Exam.model_validate(row)


__all__ = ["list_exams", "get_exam", "update_exam"]
