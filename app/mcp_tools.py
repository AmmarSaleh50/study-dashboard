"""OpenStudy MCP tool registration.

All tools live in `register_tools(server)` so the HTTP entry
(`app/mcp_http.py`, mounted at `/mcp`) registers the same catalog regardless
of how the transport is wired.

Tool descriptions are the model's only guide to what each tool does and how
it differs from its siblings — keep them disambiguating, not just
descriptive.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP, Image as MCPImage

from .schemas import (
    AppSettingsPatch,
    CourseCreate,
    CoursePatch,
    DeliverableCreate,
    DeliverablePatch,
    ExamPatch,
    LectureCreate,
    LecturePatch,
    LectureTopicsAdd,
    SlotCreate,
    SlotPatch,
    StudyTopicCreate,
    StudyTopicPatch,
    TaskCreate,
    TaskPatch,
)
from .auth import SENTINEL_USER_ID
from .intents import (
    courses as courses_intent,
    slots as slots_intent,
    exams as exams_intent,
    study_topics as topics_intent,
    deliverables as deliverables_intent,
    tasks as tasks_intent,
    events as events_intent,
    dashboard as dashboard_intent,
    lectures as lectures_intent,
    settings as settings_intent,
    files as files_intent,
)
from .services import fall_behind as fb_svc


_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")


def _parse_page_range(pages: str, total: int) -> tuple[int, int]:
    """Parse '1-20' / '5' / '3-8' into (start_idx_inclusive, end_idx_exclusive).
    Clamps to [0, total]. Caps span at 20 pages (same limit as Claude Code's Read).
    """
    m = _PAGE_RANGE_RE.match(pages or "")
    if not m:
        return (0, min(20, total))
    start = max(1, int(m.group(1)))
    end = int(m.group(2)) if m.group(2) else start
    end = min(total, max(start, end))
    # cap span at 20
    if end - start + 1 > 20:
        end = start + 19
    # to 0-indexed half-open
    return (start - 1, end)


def _jsonable(obj: Any) -> Any:
    """Recursively dump pydantic models / datetimes into JSON-friendly values."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def register_tools(server: FastMCP) -> None:
    """Register all OpenStudy tools on the given FastMCP instance."""

    # ─────────────────────── Orientation ─────────────────────

    @server.tool()
    async def get_dashboard() -> dict:
        """Full dashboard snapshot in one call: courses, schedule slots, exams,
        deliverables, tasks, lectures, study topics, plus computed fall-behind
        warnings.

        When to use: as your FIRST call for any broad question — "what's
        coming up", "how am I doing this week", "summarise my semester",
        "catch me up". Saves 7+ separate `list_*` calls.

        When NOT to use: single-entity lookups — use `get_course`,
        `list_tasks`, etc. directly."""
        return _jsonable(await dashboard_intent.get_dashboard_summary(SENTINEL_USER_ID))

    @server.tool()
    async def get_fall_behind() -> list[dict]:
        """Per-course catch-up warnings. Each entry: course_code, severity
        (ok|warn|critical), the unstudied topics (with their lecture dates),
        last_covered_on, and when the next relevant lecture is.

        Severity escalates when (a) the unstudied backlog grows and (b) the
        next lecture is imminent — so this is the right tool for "what's
        urgent?" / "what should I catch up on before tomorrow?".

        When NOT to use: to check ONE specific course — just call
        `list_study_topics(course_code=..., status='not_started')`."""
        summary = await dashboard_intent.get_dashboard_summary(SENTINEL_USER_ID)
        return _jsonable(summary.fall_behind)

    # ─────────────────────── Courses ─────────────────────────

    @server.tool()
    async def list_courses() -> list[dict]:
        """List all courses. Use when you need to discover which course codes
        exist, or to show the user their course list. If you already know the
        code, prefer `get_course`."""
        return _jsonable(await courses_intent.list_courses(SENTINEL_USER_ID))

    @server.tool()
    async def get_course(code: str) -> dict | None:
        """Fetch a single course by its code (e.g. 'ASB', 'CS101'). Returns
        None if no such course — `list_courses` first if uncertain."""
        c = await courses_intent.get_course(SENTINEL_USER_ID, code)
        return _jsonable(c) if c else None

    @server.tool()
    async def create_course(
        code: str,
        full_name: str,
        short_name: Optional[str] = None,
        module_code: Optional[str] = None,
        ects: Optional[int] = None,
        prof: Optional[str] = None,
        status_kind: Optional[str] = None,
        language: Optional[str] = None,
        color_hex: Optional[str] = None,
        folder_name: Optional[str] = None,
        exam_weight: int = 100,
        exam_retries: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Create a new course. `code` is the short identifier the user picks
        (1–8 uppercase letters/digits — e.g. 'ASB', 'CS101', 'MATH'). Every
        downstream entity (lectures, topics, deliverables, tasks, slots) is
        keyed off this code, so choose carefully — renaming is not supported.

        `color_hex` (e.g. '#7ab8ff') is the accent stripe shown in the UI;
        pick something visually distinct from existing courses. `folder_name`
        is the folder under `/opt/courses/` where the course's PDFs / notes live —
        match it to whatever folder the user keeps locally if they sync
        files.

        Errors if the code already exists; use `update_course` to modify an
        existing one."""
        if await courses_intent.get_course(SENTINEL_USER_ID, code) is not None:
            raise ValueError(f"course {code} already exists")
        body = CourseCreate(
            code=code,
            full_name=full_name,
            short_name=short_name,
            module_code=module_code,
            ects=ects,
            prof=prof,
            status_kind=status_kind,
            language=language,
            color_hex=color_hex,
            folder_name=folder_name,
            exam_weight=exam_weight,
            exam_retries=exam_retries,
            notes=notes,
        )
        return _jsonable(await courses_intent.create_course(SENTINEL_USER_ID, body))

    @server.tool()
    async def delete_course(code: str) -> dict:
        """Delete a course. CASCADES: lectures, study topics, deliverables,
        tasks, schedule slots, and the exam row for this course are all
        removed. Always ask the user to confirm before calling — this is
        irreversible."""
        if await courses_intent.get_course(SENTINEL_USER_ID, code) is None:
            raise ValueError(f"course {code} not found")
        await courses_intent.delete_course(SENTINEL_USER_ID, code)
        return {"deleted": code}

    @server.tool()
    async def update_course(
        code: str,
        full_name: Optional[str] = None,
        short_name: Optional[str] = None,
        module_code: Optional[str] = None,
        ects: Optional[int] = None,
        prof: Optional[str] = None,
        status_kind: Optional[str] = None,
        language: Optional[str] = None,
        color_hex: Optional[str] = None,
        folder_name: Optional[str] = None,
        exam_weight: Optional[int] = None,
        exam_retries: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Patch a course's mutable fields. Pass only the fields you want to
        change — omitted fields keep their existing value.

        `status_kind` is free-form (common values: 'required', 'elective').
        `color_hex` is e.g. '#7ab8ff'. `code` is immutable — if the user
        wants a different code, delete and re-create."""
        patch = CoursePatch(
            full_name=full_name,
            short_name=short_name,
            module_code=module_code,
            ects=ects,
            prof=prof,
            status_kind=status_kind,
            language=language,
            color_hex=color_hex,
            folder_name=folder_name,
            exam_weight=exam_weight,
            exam_retries=exam_retries,
            notes=notes,
        )
        return _jsonable(await courses_intent.update_course(SENTINEL_USER_ID, code, patch))

    # ─────────────────────── Schedule slots ──────────────────
    # Weekly recurring timetable entries. NOT individual lecture sessions —
    # use `list_lectures` / `create_lecture` for those.

    @server.tool()
    async def list_schedule_slots(course_code: Optional[str] = None) -> list[dict]:
        """List weekly recurring schedule slots — each row is one recurring
        class the user has on their timetable (e.g. 'Monday 10:00 lecture for
        CS101'). Filter by course_code to get one course's timetable.

        NOT individual held sessions — those are `list_lectures`."""
        return _jsonable(await slots_intent.list_slots(SENTINEL_USER_ID, course_code=course_code))

    @server.tool()
    async def create_schedule_slot(
        course_code: str,
        kind: str,
        weekday: int,
        start_time: str,
        end_time: str,
        room: Optional[str] = None,
        person: Optional[str] = None,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Create a new weekly recurring slot.

        - `kind`: 'lecture' | 'exercise' | 'tutorial' | 'lab'. German aliases
          (Vorlesung / Übung / Tutorium / Praktikum) are accepted and
          normalised.
        - `weekday`: 1=Mon … 7=Sun (ISO).
        - `start_time` / `end_time`: 'HH:MM'.
        - `starts_on` / `ends_on`: optional ISO dates constraining the
          recurrence window (typically the semester's start / end).

        To edit an existing slot, use `update_schedule_slot`. To delete,
        `delete_schedule_slot`."""
        payload = SlotCreate(
            course_code=course_code,
            kind=kind,  # type: ignore[arg-type]
            weekday=weekday,
            start_time=start_time,  # type: ignore[arg-type]
            end_time=end_time,  # type: ignore[arg-type]
            room=room,
            person=person,
            starts_on=starts_on,  # type: ignore[arg-type]
            ends_on=ends_on,  # type: ignore[arg-type]
            notes=notes,
        )
        return _jsonable(await slots_intent.create_slot(SENTINEL_USER_ID, payload))

    @server.tool()
    async def update_schedule_slot(
        slot_id: str,
        kind: Optional[str] = None,
        weekday: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        room: Optional[str] = None,
        person: Optional[str] = None,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Patch an existing weekly slot. Pass only the fields you want to
        change. `slot_id` is the uuid returned by `list_schedule_slots` /
        `create_schedule_slot`."""
        patch = SlotPatch(
            kind=kind,  # type: ignore[arg-type]
            weekday=weekday,
            start_time=start_time,  # type: ignore[arg-type]
            end_time=end_time,  # type: ignore[arg-type]
            room=room,
            person=person,
            starts_on=starts_on,  # type: ignore[arg-type]
            ends_on=ends_on,  # type: ignore[arg-type]
            notes=notes,
        )
        return _jsonable(await slots_intent.update_slot(SENTINEL_USER_ID, slot_id, patch))

    @server.tool()
    async def delete_schedule_slot(slot_id: str) -> dict:
        """Delete a weekly schedule slot by id. Non-destructive elsewhere —
        lectures already held are not affected."""
        await slots_intent.delete_slot(SENTINEL_USER_ID, slot_id)
        return {"deleted": slot_id}

    # ─────────────────────── Exams ───────────────────────────
    # One exam row per course. End-of-semester written exam — NOT the same
    # as deliverables (problem sets / projects).

    @server.tool()
    async def list_exams() -> list[dict]:
        """List end-of-semester exams — one row per course, with date,
        location, duration, aids allowed, weight, and status
        (planned|confirmed|done).

        For intermediate graded work (problem sets, projects, labs), use
        `list_deliverables` instead."""
        return _jsonable(await exams_intent.list_exams(SENTINEL_USER_ID))

    @server.tool()
    async def update_exam(
        course_code: str,
        scheduled_at: Optional[str] = None,
        duration_min: Optional[int] = None,
        location: Optional[str] = None,
        structure: Optional[str] = None,
        aids_allowed: Optional[str] = None,
        status: Optional[str] = None,
        weight_pct: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Upsert a course's exam row (creates it if missing, patches if it
        exists). Pass only fields you want to change.

        - `scheduled_at`: ISO datetime with timezone.
        - `status`: 'planned' | 'confirmed' | 'done'.
        - `aids_allowed`: free-form — e.g. 'closed book', 'one A4 cheat
          sheet', 'any notes'."""
        patch = ExamPatch(
            scheduled_at=scheduled_at,  # type: ignore[arg-type]
            duration_min=duration_min,
            location=location,
            structure=structure,
            aids_allowed=aids_allowed,
            status=status,  # type: ignore[arg-type]
            weight_pct=weight_pct,
            notes=notes,
        )
        return _jsonable(await exams_intent.update_exam(SENTINEL_USER_ID, course_code, patch))

    # ─────────────────────── Study topics ────────────────────
    # The atomic unit of "what the student is tracking progress on". One
    # topic per concept / chapter / worked example. Keyed to a lecture when
    # possible via `lecture_id` — that's how fall-behind works.

    @server.tool()
    async def list_study_topics(
        course_code: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        """List atomic study topics — the smallest unit of material the user
        tracks progress on. Each has a `status`
        (not_started|in_progress|studied|mastered|struggling) and optional
        `confidence` (0–5).

        When to use: "what do I still need to study", "what am I behind on",
        "show me my progress in CS101". Filter by `course_code` and/or
        `status` to narrow.

        When NOT to use: don't confuse with `list_lectures` (held sessions)
        or `list_deliverables` (graded submissions)."""
        return _jsonable(await topics_intent.list_study_topics(SENTINEL_USER_ID, course_code=course_code, status=status))

    @server.tool()
    async def create_study_topic(
        course_code: str,
        name: str,
        chapter: Optional[str] = None,
        description: Optional[str] = None,
        kind: Optional[str] = None,
        covered_on: Optional[str] = None,
        lecture_id: Optional[str] = None,
        status: str = "not_started",
        confidence: Optional[int] = None,
        notes: Optional[str] = None,
        sort_order: int = 0,
    ) -> dict:
        """Add a single study topic.

        Prefer `add_lecture_topics` when you're adding MULTIPLE topics from
        the same lecture — it's one call and also creates the Lecture row
        for you.

        - `kind`: 'lecture' | 'exercise' | 'reading' (German aliases accepted).
        - `covered_on`: ISO date when the lecture introduced this topic —
          required for fall-behind detection.
        - `lecture_id`: preferred over `covered_on` alone, since it lets the
          UI jump from topic → lecture.
        - `description`: the rich content / Skript text. `notes` is the
          user's own scribbles, kept separate."""
        payload = StudyTopicCreate(
            course_code=course_code,  # type: ignore[arg-type]
            chapter=chapter,
            name=name,
            description=description,
            kind=kind,  # type: ignore[arg-type]
            covered_on=covered_on,  # type: ignore[arg-type]
            lecture_id=lecture_id,
            status=status,  # type: ignore[arg-type]
            confidence=confidence,
            notes=notes,
            sort_order=sort_order,
        )
        return _jsonable(await topics_intent.create_study_topic(SENTINEL_USER_ID, payload))

    @server.tool()
    async def update_study_topic(
        topic_id: str,
        chapter: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        kind: Optional[str] = None,
        covered_on: Optional[str] = None,
        lecture_id: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[int] = None,
        notes: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> dict:
        """Patch an existing study topic. When `status` transitions to
        `studied` or `mastered`, `last_reviewed_at` is stamped automatically.

        Prefer `mark_studied` for the common status='studied' case, and
        `set_confidence` for setting just the confidence number — both are
        less error-prone than building the full patch."""
        patch = StudyTopicPatch(
            chapter=chapter,
            name=name,
            description=description,
            kind=kind,  # type: ignore[arg-type]
            covered_on=covered_on,  # type: ignore[arg-type]
            lecture_id=lecture_id,
            status=status,  # type: ignore[arg-type]
            confidence=confidence,
            notes=notes,
            sort_order=sort_order,
        )
        return _jsonable(await topics_intent.update_study_topic(SENTINEL_USER_ID, topic_id, patch))

    @server.tool()
    async def mark_studied(topic_id: str) -> dict:
        """Shortcut: set a topic's status to 'studied' and stamp
        last_reviewed_at. Equivalent to `update_study_topic(topic_id,
        status='studied')` — prefer this shortcut for the common case."""
        return _jsonable(await topics_intent.update_study_topic(SENTINEL_USER_ID, topic_id, StudyTopicPatch(status="studied")))

    @server.tool()
    async def set_confidence(topic_id: str, confidence: int) -> dict:
        """Shortcut: set a topic's confidence (0–5). 0 = no idea, 5 = could
        teach it. Confidence is independent of status — a topic can be
        'studied' but low-confidence.

        Tip: if the user says something like "I looked at it but still don't
        get it", mark_studied + set_confidence=1 captures that cleanly."""
        if confidence < 0 or confidence > 5:
            raise ValueError("confidence must be 0..5")
        return _jsonable(await topics_intent.update_study_topic(SENTINEL_USER_ID, topic_id, StudyTopicPatch(confidence=confidence)))

    @server.tool()
    async def add_lecture_topics(
        course_code: str,
        covered_on: str,
        topics: list[dict],
        kind: str = "lecture",
        lecture_id: Optional[str] = None,
        create_lecture_number: Optional[int] = None,
        create_lecture_title: Optional[str] = None,
    ) -> list[dict]:
        """Bulk-record topics covered in one lecture session. Preferred over
        looping `create_study_topic` — faster and creates a Lecture row too.

        `topics` is a list of dicts:
        {chapter?, name, description?, status?, confidence?, notes?, sort_order?}
        — `name` is required per topic; everything else optional.

        `kind` applies to every topic (the study-topic kind enum:
        lecture|exercise|reading). It is NOT the slot/lecture kind — for
        that, pass it via `create_lecture_*` parameters.

        Default status per topic is 'not_started' — `covered_on` already
        signals "introduced in class". Only use 'studied' / 'mastered' when
        the user has actually self-studied the material.

        Lecture linkage:
        - Pass `lecture_id` to link to an EXISTING lecture row.
        - Pass `create_lecture_number` (and optionally `create_lecture_title`)
          to have this call create a new Lecture row inline and link every
          topic to it.
        - Pass neither: topics are unlinked (still tracked via covered_on)."""
        create_lecture = None
        if lecture_id is None and create_lecture_number is not None:
            create_lecture = LectureCreate(
                course_code=course_code,  # type: ignore[arg-type]
                number=create_lecture_number,
                held_on=covered_on,  # type: ignore[arg-type]
                kind=kind,  # type: ignore[arg-type]
                title=create_lecture_title,
                attended=True,
            )
        payload = LectureTopicsAdd(
            course_code=course_code,  # type: ignore[arg-type]
            covered_on=covered_on,  # type: ignore[arg-type]
            kind=kind,  # type: ignore[arg-type]
            topics=topics,
            lecture_id=lecture_id,
            create_lecture=create_lecture,
        )
        return _jsonable(await topics_intent.add_lecture_topics(SENTINEL_USER_ID, payload))

    @server.tool()
    async def delete_study_topic(topic_id: str) -> dict:
        """Delete a study topic by id. Safe — doesn't cascade. If the user
        just wants to stop tracking progress, consider
        `update_study_topic(status='skipped'-equivalent)` instead — but
        there's no skipped status, so deletion is usually fine."""
        await topics_intent.delete_study_topic(SENTINEL_USER_ID, topic_id)
        return {"deleted": topic_id}

    # ─────────────────────── Deliverables ────────────────────
    # Graded submissions with due dates. NOT personal todos (use tasks) and
    # NOT the end-of-semester exam (use exams).

    @server.tool()
    async def list_deliverables(
        course_code: Optional[str] = None,
        status: Optional[str] = None,
        due_before: Optional[str] = None,
    ) -> list[dict]:
        """List graded submissions: problem sets, projects, labs, etc. Each
        has a due_at and a status
        (open|in_progress|submitted|graded|skipped).

        When to use: "what's due this week", "what do I still have to hand
        in". Filter with `due_before` (ISO datetime) for time-boxed
        questions.

        NOT for personal todos (use `list_tasks`) or the end-of-semester
        exam (use `list_exams`)."""
        due = datetime.fromisoformat(due_before) if due_before else None
        return _jsonable(
            await deliverables_intent.list_deliverables(
                SENTINEL_USER_ID, course_code=course_code, status=status, due_before=due
            )
        )

    @server.tool()
    async def create_deliverable(
        course_code: str,
        name: str,
        due_at: str,
        kind: Optional[str] = None,
        available_at: Optional[str] = None,
        status: str = "open",
        local_path: Optional[str] = None,
        external_url: Optional[str] = None,
        weight_info: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Create a new graded submission.

        - `kind`: 'submission' | 'project' | 'lab' | 'block' (German aliases
          'abgabe' / 'praktikum' accepted).
        - `due_at`: ISO datetime WITH timezone (e.g.
          '2026-04-25T23:59:00+02:00'). Use `get_app_settings` if you need
          the user's timezone.
        - `available_at`: when the submission becomes available (optional)."""
        payload = DeliverableCreate(
            course_code=course_code,  # type: ignore[arg-type]
            kind=kind,  # type: ignore[arg-type]
            name=name,
            available_at=available_at,  # type: ignore[arg-type]
            due_at=due_at,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            local_path=local_path,
            external_url=external_url,
            weight_info=weight_info,
            notes=notes,
        )
        return _jsonable(await deliverables_intent.create_deliverable(SENTINEL_USER_ID, payload))

    @server.tool()
    async def update_deliverable(
        deliverable_id: str,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        available_at: Optional[str] = None,
        due_at: Optional[str] = None,
        status: Optional[str] = None,
        local_path: Optional[str] = None,
        external_url: Optional[str] = None,
        weight_info: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Patch a deliverable. Prefer `mark_deliverable_submitted` for the
        common status='submitted' case."""
        patch = DeliverablePatch(
            kind=kind,  # type: ignore[arg-type]
            name=name,
            available_at=available_at,  # type: ignore[arg-type]
            due_at=due_at,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            local_path=local_path,
            external_url=external_url,
            weight_info=weight_info,
            notes=notes,
        )
        return _jsonable(await deliverables_intent.update_deliverable(SENTINEL_USER_ID, deliverable_id, patch))

    @server.tool()
    async def mark_deliverable_submitted(deliverable_id: str) -> dict:
        """Shortcut: flip a deliverable to status='submitted' and stamp
        submitted_at. Prefer this over `update_deliverable` for the common
        "I handed it in" case."""
        return _jsonable(await deliverables_intent.mark_submitted(SENTINEL_USER_ID, deliverable_id))

    @server.tool()
    async def delete_deliverable(deliverable_id: str) -> dict:
        """Delete a deliverable by id. Typically only used when it was added
        by mistake — use `update_deliverable(status='skipped')` if the user
        decided to skip it instead."""
        await deliverables_intent.delete_deliverable(SENTINEL_USER_ID, deliverable_id)
        return {"deleted": deliverable_id}

    # ─────────────────────── Tasks ───────────────────────────
    # Personal todos. Anything that isn't a scheduled class, graded
    # deliverable, or exam — reminders, errands, reading, etc.

    @server.tool()
    async def list_tasks(
        course_code: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        due_before: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[dict]:
        """List personal todos. Status:
        open|in_progress|done|skipped|blocked. Priority:
        low|med|high|urgent.

        When to use: "what should I do today", "what's on my todo list".
        Filter by `course_code` (optional — tasks can be unattached) or
        other params.

        NOT for graded submissions (`list_deliverables`) or study progress
        (`list_study_topics`)."""
        due = datetime.fromisoformat(due_before) if due_before else None
        return _jsonable(
            await tasks_intent.list_tasks(
                SENTINEL_USER_ID, course_code=course_code, status=status, priority=priority, due_before=due, tag=tag
            )
        )

    @server.tool()
    async def create_task(
        title: str,
        course_code: Optional[str] = None,
        description: Optional[str] = None,
        due_at: Optional[str] = None,
        priority: str = "med",
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Create a personal todo. `priority`: low|med|high|urgent. `due_at`
        is ISO datetime and optional — tasks without due dates are fine.

        Tasks can be standalone (no `course_code`) or attached to a course
        for grouping in the UI."""
        payload = TaskCreate(
            course_code=course_code,  # type: ignore[arg-type]
            title=title,
            description=description,
            due_at=due_at,  # type: ignore[arg-type]
            status="open",
            priority=priority,  # type: ignore[arg-type]
            tags=tags,
        )
        return _jsonable(await tasks_intent.create_task(SENTINEL_USER_ID, payload))

    @server.tool()
    async def update_task(
        task_id: str,
        course_code: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_at: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Patch a task. Setting status='done' stamps completed_at. Prefer
        `complete_task` for the common completion case, and `reopen_task`
        if you want to undo a completion."""
        patch = TaskPatch(
            course_code=course_code,  # type: ignore[arg-type]
            title=title,
            description=description,
            due_at=due_at,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            priority=priority,  # type: ignore[arg-type]
            tags=tags,
        )
        return _jsonable(await tasks_intent.update_task(SENTINEL_USER_ID, task_id, patch))

    @server.tool()
    async def complete_task(task_id: str) -> dict:
        """Shortcut: mark a task as done and stamp completed_at. Prefer this
        over `update_task(status='done')` for the common completion case."""
        return _jsonable(await tasks_intent.complete_task(SENTINEL_USER_ID, task_id))

    @server.tool()
    async def reopen_task(task_id: str) -> dict:
        """Shortcut: revert a done task back to 'open' and clear
        completed_at. For when the user said "done" prematurely."""
        return _jsonable(await tasks_intent.reopen_task(SENTINEL_USER_ID, task_id))

    @server.tool()
    async def delete_task(task_id: str) -> dict:
        """Delete a task by id. Safe — no cascades."""
        await tasks_intent.delete_task(SENTINEL_USER_ID, task_id)
        return {"deleted": task_id}

    # ─────────────────────── Lectures ────────────────────────
    # Individual held sessions on specific dates. NOT the weekly timetable
    # (that's schedule_slots). Each lecture can have many study_topics
    # linked to it.

    @server.tool()
    async def list_lectures(course_code: Optional[str] = None) -> list[dict]:
        """List individual lecture sessions — one row per session held on a
        specific date (number, held_on, attended, title, summary). Ordered
        by course_code then number.

        NOT the recurring timetable (that's `list_schedule_slots`)."""
        return _jsonable(await lectures_intent.list_lectures(SENTINEL_USER_ID, course_code=course_code))

    @server.tool()
    async def create_lecture(
        course_code: str,
        number: Optional[int] = None,
        held_on: Optional[str] = None,
        kind: Optional[str] = "lecture",
        title: Optional[str] = None,
        summary: Optional[str] = None,
        attended: bool = False,
        notes: Optional[str] = None,
    ) -> dict:
        """Create a lecture session row.

        Most of the time prefer `add_lecture_topics` with
        `create_lecture_number` — that creates the Lecture AND its topics in
        one call, which is almost always what you want after a lecture
        happens.

        - `kind`: 'lecture' | 'exercise' | 'tutorial' | 'lab' (German aliases
          accepted).
        - `held_on`: ISO date.
        - `number`: the sequence within the course (1, 2, 3 …)."""
        payload = LectureCreate(
            course_code=course_code,  # type: ignore[arg-type]
            number=number,
            held_on=held_on,  # type: ignore[arg-type]
            kind=kind,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            attended=attended,
            notes=notes,
        )
        return _jsonable(await lectures_intent.create_lecture(SENTINEL_USER_ID, payload))

    @server.tool()
    async def update_lecture(
        lecture_id: str,
        number: Optional[int] = None,
        held_on: Optional[str] = None,
        kind: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        attended: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Patch a lecture. Prefer `mark_lecture_attended` for the common
        attended-toggle case."""
        patch = LecturePatch(
            number=number,
            held_on=held_on,  # type: ignore[arg-type]
            kind=kind,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            attended=attended,
            notes=notes,
        )
        return _jsonable(await lectures_intent.update_lecture(SENTINEL_USER_ID, lecture_id, patch))

    @server.tool()
    async def mark_lecture_attended(lecture_id: str, attended: bool = True) -> dict:
        """Shortcut: flip a lecture's `attended` flag. Call with
        attended=False to un-mark."""
        return _jsonable(await lectures_intent.mark_attended(SENTINEL_USER_ID, lecture_id, attended=attended))

    @server.tool()
    async def delete_lecture(lecture_id: str) -> dict:
        """Delete a lecture. Linked study topics keep existing — their
        lecture_id is cleared to null, not cascaded."""
        await lectures_intent.delete_lecture(SENTINEL_USER_ID, lecture_id)
        return {"deleted": lecture_id}

    # ─────────────────────── Reopen helpers ──────────────────

    @server.tool()
    async def reopen_deliverable(deliverable_id: str) -> dict:
        """Shortcut: revert a submitted deliverable back to 'open'. For
        "wait, I actually haven't handed it in yet" cases."""
        return _jsonable(await deliverables_intent.reopen_deliverable(SENTINEL_USER_ID, deliverable_id))

    # ─────────────────────── Events (activity log) ───────────

    @server.tool()
    async def list_events(
        since: Optional[str] = None,
        kind: Optional[str] = None,
        course_code: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """List activity log entries (newest first). Used for audit / history
        — "what did I study this week", "show my recent activity".

        `since`: ISO datetime cutoff. `kind`: free-form kind label. NOT for
        tracking what needs doing — that's `list_tasks` / `list_deliverables`."""
        s = datetime.fromisoformat(since) if since else None
        return _jsonable(
            await events_intent.list_events(SENTINEL_USER_ID, since=s, kind=kind, course_code=course_code, limit=limit)
        )

    @server.tool()
    async def record_event(
        kind: str,
        course_code: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> dict:
        """Log an activity event — study sessions, reading notes, anything
        worth remembering but not worth a Task or Topic row. `kind` is
        free-form (e.g. 'study_session', 'reading', 'meeting').

        Prefer this over creating a throwaway Task when the user is reporting
        something that's already done."""
        from .schemas import EventCreate

        return _jsonable(
            await events_intent.record_event(
                SENTINEL_USER_ID,
                EventCreate(kind=kind, course_code=course_code, payload=payload),
            )
        )

    # ─────────────────────── App settings (profile) ──────────

    @server.tool()
    async def get_app_settings() -> dict:
        """Get the user's profile + semester config (display_name, monogram,
        institution, semester_label, semester_start, semester_end, timezone,
        locale).

        Call this FIRST before any time-sensitive work — knowing the user's
        timezone prevents deadline-off-by-hours bugs, and knowing
        semester_start/end lets you compute "week N" correctly."""
        return _jsonable(await settings_intent.get_settings(SENTINEL_USER_ID))

    @server.tool()
    async def update_app_settings(
        display_name: Optional[str] = None,
        monogram: Optional[str] = None,
        institution: Optional[str] = None,
        semester_label: Optional[str] = None,
        semester_start: Optional[str] = None,
        semester_end: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> dict:
        """Patch profile + semester fields. Pass only what you want to
        change.

        - Dates (semester_start / semester_end): 'YYYY-MM-DD'.
        - `timezone`: IANA ID ('Europe/Berlin', 'America/New_York',
          'Asia/Dubai'). Affects every deadline-time calculation.
        - `locale`: BCP-47 ('en-US', 'de-DE') — controls UI date formatting.
        - `monogram`: 1–3 chars shown in the sidebar crest."""
        patch = AppSettingsPatch(
            display_name=display_name,
            monogram=monogram,
            institution=institution,
            semester_label=semester_label,
            semester_start=semester_start,  # type: ignore[arg-type]
            semester_end=semester_end,  # type: ignore[arg-type]
            timezone=timezone,
            locale=locale,
        )
        return _jsonable(await settings_intent.update_settings(SENTINEL_USER_ID, patch))

    # ─────────────────────── Meta ─────────────────────────────

    @server.tool()
    async def now_here() -> dict:
        """Current datetime in the user's configured timezone (falls back to
        UTC if unset). Use this whenever you need "now" for relative-time
        calculations — your own clock might be in a different zone than the
        user's deadlines."""
        from zoneinfo import ZoneInfo

        try:
            settings_obj = await settings_intent.get_settings(SENTINEL_USER_ID)
            tz_name = settings_obj.timezone or "UTC"
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
        now = datetime.now(tz=tz)
        return {"iso": now.isoformat(), "utc_iso": now.astimezone(timezone.utc).isoformat()}

    # ─────────────────────── Course files (filesystem under /opt/courses) ─────────

    @server.tool()
    async def list_course_files(prefix: str = "", limit: int = 200) -> list[dict]:
        """Browse the course tree on disk — the user's course PDFs, notes,
        slides, etc. Structure typically mirrors a local per-course folder
        layout.

        - prefix='' → top-level entries (typically one folder per course).
        - prefix='<course-folder>' → files + subfolders one level deep.
        - prefix='<course-folder>/Week1' → files in that week's folder.

        The list is NOT recursive — drill down by passing a
        folder's path as the next prefix.

        Each entry: {name, path, type}. type='folder' or 'file'. Files also
        carry size, content_type, updated_at.

        To read a file's contents, pass its `path` to `read_course_file`."""
        clean = (prefix or "").strip().strip("/")
        entries = await files_intent.list_files(SENTINEL_USER_ID, clean, limit=limit)
        out: list[dict] = []
        for e in entries:
            name = e.get("name") or ""
            if not name:
                continue
            path = f"{clean}/{name}" if clean else name
            if e.get("id") is None:
                out.append({"name": name, "path": path, "type": "folder"})
            else:
                meta = e.get("metadata") or {}
                out.append(
                    {
                        "name": name,
                        "path": path,
                        "type": "file",
                        "size": meta.get("size"),
                        "content_type": meta.get("mimetype"),
                        "updated_at": e.get("updated_at"),
                    }
                )
        return out

    @server.tool()
    async def read_course_file(path: str, pages: str = "1-20") -> list:
        """Read a file from the course tree on disk. Auto-detects by extension:
          - .md / .txt → plain text
          - .ipynb     → parsed notebook (cells inline as text)
          - .pdf       → requested page range rendered as PNG images (multimodal)
                         plus a text-extraction fallback of the same pages
          - .png/.jpg/.jpeg/.webp → the image as-is

        `pages` accepts '1-20', '5', '3-8' (1-indexed, inclusive). Caps at 20
        pages per call — same as Claude Code's native Read tool.

        Returns a list of content items. For PDFs, the LLM sees the rendered
        pages directly; the text block is a backup in case the client doesn't
        feed tool-returned images to the model.

        To browse, use `list_course_files` first."""
        data = await files_intent.download(SENTINEL_USER_ID, path)
        ext = (path.rsplit(".", 1)[-1] if "." in path else "").lower()

        if ext in ("md", "txt", ""):
            try:
                return [data.decode("utf-8")]
            except UnicodeDecodeError:
                return [data.decode("utf-8", errors="replace")]

        if ext == "ipynb":
            try:
                nb = json.loads(data.decode("utf-8"))
            except Exception as exc:
                return [f"Failed to parse notebook: {exc}"]
            lines: list[str] = []
            for i, cell in enumerate(nb.get("cells", [])):
                kind = cell.get("cell_type", "?")
                src = "".join(cell.get("source", []))
                lines.append(f"## Cell {i} [{kind}]\n{src}\n")
            return ["\n".join(lines)]

        if ext in ("png", "jpg", "jpeg", "webp"):
            fmt = "jpeg" if ext == "jpg" else ext
            return [MCPImage(data=data, format=fmt)]

        if ext == "pdf":
            import fitz  # pymupdf

            doc = fitz.open(stream=data, filetype="pdf")
            total = doc.page_count
            start, end = _parse_page_range(pages, total)

            items: list[Any] = []
            for p in range(start, end):
                pix = doc[p].get_pixmap(dpi=120)
                items.append(MCPImage(data=pix.tobytes("png"), format="png"))
            doc.close()
            return items

        return [
            f"Unsupported file type `.{ext}`. "
            f"Supported: .pdf, .md, .txt, .ipynb, .png, .jpg, .jpeg, .webp"
        ]

    @server.tool()
    def notify_telegram(text: str, parse_mode: str | None = None) -> dict:
        """Send a Telegram message to the operator's pre-configured chat.

        Used by background agents that can't reach the Telegram API directly
        from their runtime — they call this server-side tool and the backend
        (unrestricted egress) forwards the message.

        Pass ``parse_mode="HTML"`` for ``<b>``, ``<i>``, ``<code>`` and
        ``<a href="...">`` formatting (only ``<``, ``>``, ``&`` need
        escaping as ``&lt; &gt; &amp;``). HTML is preferred over Markdown
        because the escape rules are simpler. Omit ``parse_mode`` for
        plain text.

        Configured via ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` on the
        server. Returns ``{"ok": True, "message_id": <int>}`` on success or
        ``{"ok": False, "error": "<reason>"}`` on failure.
        """
        import os
        import httpx

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured"}
        if not text or not text.strip():
            return {"ok": False, "error": "empty text"}
        payload: dict = {
            "chat_id": int(chat_id),
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=15.0,
            )
            data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "error": str(data)}
            return {"ok": True, "message_id": data["result"]["message_id"]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Keep a reference so fb_svc is not flagged as unused (services/dashboard.py re-exports it).
    _ = fb_svc
