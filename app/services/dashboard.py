from datetime import datetime, timezone
from uuid import UUID

from ..schemas import DashboardSummary
from . import (
    courses as courses_svc,
    slots as slots_svc,
    exams as exams_svc,
    deliverables as deliverables_svc,
    tasks as tasks_svc,
    study_topics as topics_svc,
    lectures as lectures_svc,
    fall_behind as fb_svc,
)


async def get_dashboard_summary(user_id: UUID) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    cs = await courses_svc.list_courses(user_id)
    ss = await slots_svc.list_slots(user_id)
    es = await exams_svc.list_exams(user_id)
    ds = await deliverables_svc.list_deliverables(user_id)
    ts = await tasks_svc.list_tasks(user_id)
    tp = await topics_svc.list_study_topics()
    ls = await lectures_svc.list_lectures(user_id)
    fb = fb_svc.compute_fall_behind(cs, tp, ss, now)
    return DashboardSummary(
        now=now,
        courses=cs,
        slots=ss,
        exams=es,
        deliverables=ds,
        tasks=ts,
        study_topics=tp,
        lectures=ls,
        fall_behind=fb,
    )
