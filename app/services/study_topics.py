from datetime import datetime, timezone
from typing import List, Optional

from .. import db
from ..schemas import LectureTopicsAdd, StudyTopic, StudyTopicCreate, StudyTopicPatch
from ._helpers import model_dump_clean


async def list_study_topics(
    course_code: Optional[str] = None, status: Optional[str] = None
) -> List[StudyTopic]:
    where: list[str] = []
    args: list = []
    if course_code:
        where.append("course_code = %s")
        args.append(course_code)
    if status:
        where.append("status = %s")
        args.append(status)
    sql = "SELECT * FROM study_topics"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY course_code, sort_order"
    rows = await db.fetch(sql, *args)
    return [StudyTopic.model_validate(r) for r in rows]


async def create_study_topic(payload: StudyTopicCreate) -> StudyTopic:
    data = model_dump_clean(payload)
    cols = list(data.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    row = await db.fetchrow(
        f"INSERT INTO study_topics ({', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create study topic for {payload.course_code}")
    return StudyTopic.model_validate(row)


async def update_study_topic(topic_id: str, patch: StudyTopicPatch) -> StudyTopic:
    data = model_dump_clean(patch)
    if not data:
        raise ValueError("empty patch")
    if data.get("status") in ("studied", "mastered"):
        data["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    cols = list(data.keys())
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE study_topics SET {set_clause} WHERE id = %s RETURNING *",
        *[data[c] for c in cols], topic_id,
    )
    if row is None:
        raise ValueError(f"study topic {topic_id} not found")
    return StudyTopic.model_validate(row)


async def delete_study_topic(topic_id: str) -> None:
    await db.execute("DELETE FROM study_topics WHERE id = %s", topic_id)


async def add_lecture_topics(payload: LectureTopicsAdd) -> List[StudyTopic]:
    # Resolve/create the lecture if needed
    lecture_id = payload.lecture_id
    if payload.create_lecture and not lecture_id:
        from . import lectures as lectures_svc
        lec = await lectures_svc.create_lecture(payload.create_lecture)
        lecture_id = lec.id
    rows: list[dict] = []
    for idx, t in enumerate(payload.topics):
        row = {
            "course_code": payload.course_code,
            "chapter": t.get("chapter"),
            "name": t["name"],
            "description": t.get("description"),
            "kind": payload.kind,
            "covered_on": payload.covered_on.isoformat(),
            "lecture_id": lecture_id,
            "status": t.get("status", "not_started"),
            "confidence": t.get("confidence"),
            "notes": t.get("notes"),
            "sort_order": t.get("sort_order", idx),
        }
        rows.append({k: v for k, v in row.items() if v is not None})
    # Each row may have a different column set (sparse — None values dropped),
    # so we INSERT row-by-row instead of executemany (which needs fixed columns).
    # At OpenStudy's scale (a lecture has ~3-10 topics), this is fine.
    inserted: list[StudyTopic] = []
    for row in rows:
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        inserted_row = await db.fetchrow(
            f"INSERT INTO study_topics ({', '.join(cols)}) "
            f"VALUES ({placeholders}) RETURNING *",
            *[row[c] for c in cols],
        )
        if inserted_row is None:
            raise ValueError(
                f"failed to insert study topic '{row.get('name')}' for "
                f"{payload.course_code}"
            )
        inserted.append(StudyTopic.model_validate(inserted_row))
    return inserted
