from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from .. import db
from ..schemas import LectureTopicsAdd, LectureCreate, StudyTopic, StudyTopicCreate, StudyTopicPatch
from ._helpers import model_dump_clean, validated_cols


async def list_study_topics(
    user_id: UUID,
    course_code: Optional[str] = None,
    status: Optional[str] = None,
) -> List[StudyTopic]:
    where: list[str] = ["user_id = %s"]
    args: list = [user_id]
    if course_code:
        where.append("course_code = %s")
        args.append(course_code)
    if status:
        where.append("status = %s")
        args.append(status)
    sql = "SELECT * FROM study_topics WHERE " + " AND ".join(where)
    sql += " ORDER BY course_code, sort_order"
    rows = await db.fetch(sql, *args)
    return [StudyTopic.model_validate(r) for r in rows]


async def create_study_topic(user_id: UUID, payload: StudyTopicCreate) -> StudyTopic:
    data = model_dump_clean(payload)
    cols = validated_cols(StudyTopicCreate, data)
    placeholders = ", ".join(["%s"] * (len(cols) + 1))
    row = await db.fetchrow(
        f"INSERT INTO study_topics (user_id, {', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        user_id, *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create study topic for {payload.course_code}")
    return StudyTopic.model_validate(row)


async def update_study_topic(user_id: UUID, topic_id: str, patch: StudyTopicPatch) -> StudyTopic:
    data = model_dump_clean(patch)
    if not data:
        raise ValueError("empty patch")
    if data.get("status") in ("studied", "mastered"):
        data["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    # Validate against StudyTopic (the read model, superset of all DB columns)
    # since `last_reviewed_at` is injected here but isn't on StudyTopicPatch.
    cols = validated_cols(StudyTopic, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE study_topics SET {set_clause} WHERE id = %s AND user_id = %s RETURNING *",
        *[data[c] for c in cols], topic_id, user_id,
    )
    if row is None:
        raise ValueError(f"study topic {topic_id} not found")
    return StudyTopic.model_validate(row)


async def delete_study_topic(user_id: UUID, topic_id: str) -> None:
    await db.execute(
        "DELETE FROM study_topics WHERE id = %s AND user_id = %s", topic_id, user_id
    )


async def add_lecture_topics(user_id: UUID, payload: LectureTopicsAdd) -> List[StudyTopic]:
    """Atomically create-lecture-and-insert-topics, OR insert-topics-only.

    The optional lecture creation + every topic insert run inside a single
    psycopg transaction (one connection, implicit BEGIN at first execute,
    COMMIT on clean exit, ROLLBACK on exception). Without this, a topic
    insert failing mid-loop would leave the lecture row + earlier topics
    committed — partial writes the caller has no clean way to recover from.
    """
    # Build all the topic rows up front so we don't go to the DB for nothing
    # if the payload is malformed.
    topic_rows: list[dict] = []
    for idx, t in enumerate(payload.topics):
        row = {
            "course_code": payload.course_code,
            "chapter": t.get("chapter"),
            "name": t["name"],
            "description": t.get("description"),
            "kind": payload.kind,
            "covered_on": payload.covered_on.isoformat(),
            # `lecture_id` is filled in below — may be None until we know it.
            "lecture_id": payload.lecture_id,
            "status": t.get("status", "not_started"),
            "confidence": t.get("confidence"),
            "notes": t.get("notes"),
            "sort_order": t.get("sort_order", idx),
        }
        topic_rows.append({k: v for k, v in row.items() if v is not None})

    inserted: list[StudyTopic] = []
    async with db.db() as conn, conn.cursor() as cur:
        # 1. Resolve/create the lecture in this transaction. We inline the
        #    INSERT (rather than calling `lectures_svc.create_lecture`)
        #    because that helper opens its own pool connection — using it
        #    here would commit mid-flow and break atomicity.
        lecture_id = payload.lecture_id
        if payload.create_lecture and not lecture_id:
            lec_data = model_dump_clean(payload.create_lecture)
            lec_cols = validated_cols(LectureCreate, lec_data)
            lec_placeholders = ", ".join(["%s"] * (len(lec_cols) + 1))
            await cur.execute(
                f"INSERT INTO lectures (user_id, {', '.join(lec_cols)}) "
                f"VALUES ({lec_placeholders}) RETURNING id",
                [user_id, *[lec_data[c] for c in lec_cols]],
            )
            lec_row = await cur.fetchone()
            if lec_row is None:
                raise ValueError("failed to create lecture")
            lecture_id = lec_row["id"]
            # Backfill lecture_id into each topic row
            for r in topic_rows:
                r["lecture_id"] = lecture_id
        elif lecture_id:
            # Verify that the referenced lecture belongs to this user.
            await cur.execute(
                "SELECT id FROM lectures WHERE id = %s AND user_id = %s LIMIT 1",
                [lecture_id, user_id],
            )
            if await cur.fetchone() is None:
                raise ValueError(f"lecture {lecture_id} not found")

        # 2. Insert topics. Each row may have a different column set
        #    (sparse — None values dropped), so we INSERT row-by-row instead
        #    of executemany (which needs fixed columns). All inserts share
        #    this transaction.
        for row in topic_rows:
            cols = validated_cols(StudyTopicCreate, row)
            placeholders = ", ".join(["%s"] * (len(cols) + 1))
            await cur.execute(
                f"INSERT INTO study_topics (user_id, {', '.join(cols)}) "
                f"VALUES ({placeholders}) RETURNING *",
                [user_id, *[row[c] for c in cols]],
            )
            inserted_row = await cur.fetchone()
            if inserted_row is None:
                raise ValueError(
                    f"failed to insert study topic '{row.get('name')}' for "
                    f"{payload.course_code}"
                )
            inserted.append(StudyTopic.model_validate(inserted_row))
    return inserted
