from datetime import datetime, timezone

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


async def get_dashboard_summary() -> DashboardSummary:
    now = datetime.now(timezone.utc)
    cs = await courses_svc.list_courses()
    ss = await slots_svc.list_slots()
    es = await exams_svc.list_exams()
    ds = await deliverables_svc.list_deliverables()
    ts = await tasks_svc.list_tasks()
    tp = await topics_svc.list_study_topics()
    ls = await lectures_svc.list_lectures()
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
