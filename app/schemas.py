"""Pydantic models mirroring the database schema (see migrations/).

Enum values are English-canonical. German values from legacy data or old MCP
integrations are accepted on input and normalized at validation time — see the
`_*_ALIASES` maps below.
"""
from datetime import date, datetime, time
from typing import Annotated, Any, List, Literal, Optional
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

# A course code is a short uppercase identifier the user picks (e.g. "ASB", "CS101", "MATH").
# 1–8 characters, letters + digits.
CourseCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=8, pattern=r"^[A-Z0-9]+$"),
]

# ---------- Enum normalization ----------
# Canonical kind values are English. Legacy German spellings are accepted on
# input and normalized at validation time so existing integrations keep working.
_SLOT_KIND_ALIASES = {
    "vorlesung": "lecture",
    "übung":     "exercise",
    "uebung":    "exercise",
    "tutorium":  "tutorial",
    "praktikum": "lab",
}
_STUDY_TOPIC_KIND_ALIASES = {
    "vorlesung": "lecture",
    "übung":     "exercise",
    "uebung":    "exercise",
}
_DELIVERABLE_KIND_ALIASES = {
    "abgabe":    "submission",
    "praktikum": "lab",
}


def _normalize(aliases: dict[str, str]):
    def fn(v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip().lower()
            return aliases.get(s, s)
        return v
    return fn


SlotKind = Annotated[
    Literal["lecture", "exercise", "tutorial", "lab"],
    BeforeValidator(_normalize(_SLOT_KIND_ALIASES)),
]
StudyTopicKind = Annotated[
    Literal["lecture", "exercise", "reading"],
    BeforeValidator(_normalize(_STUDY_TOPIC_KIND_ALIASES)),
]
DeliverableKind = Annotated[
    Literal["submission", "project", "lab", "block"],
    BeforeValidator(_normalize(_DELIVERABLE_KIND_ALIASES)),
]

StudyTopicStatus = Literal[
    "not_started", "in_progress", "studied", "mastered", "struggling"
]
DeliverableStatus = Literal[
    "open", "in_progress", "submitted", "graded", "skipped"
]
TaskStatus = Literal["open", "in_progress", "done", "skipped", "blocked"]
TaskPriority = Literal["low", "med", "high", "urgent"]
ExamStatus = Literal["planned", "confirmed", "done"]
FallBehindSeverity = Literal["ok", "warn", "critical"]


# ---------- App settings ----------
class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    display_name: Optional[str] = None
    monogram: Optional[str] = None
    institution: Optional[str] = None
    semester_label: Optional[str] = None
    semester_start: Optional[date] = None
    semester_end: Optional[date] = None
    timezone: str = "UTC"
    locale: str = "en-US"
    theme: Optional[str] = "editorial"


class AppSettingsPatch(BaseModel):
    display_name: Optional[str] = None
    monogram: Optional[str] = None
    institution: Optional[str] = None
    semester_label: Optional[str] = None
    semester_start: Optional[date] = None
    semester_end: Optional[date] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    theme: Optional[str] = None


# ---------- Course ----------
class CourseCreate(BaseModel):
    code: CourseCode
    full_name: str
    short_name: Optional[str] = None
    module_code: Optional[str] = None
    ects: Optional[int] = None
    prof: Optional[str] = None
    status_kind: Optional[str] = None
    language: Optional[str] = None
    color_hex: Optional[str] = None
    folder_name: Optional[str] = None
    exam_weight: int = 100
    exam_retries: Optional[int] = None
    notes: Optional[str] = None


class CoursePatch(BaseModel):
    full_name: Optional[str] = None
    short_name: Optional[str] = None
    module_code: Optional[str] = None
    ects: Optional[int] = None
    prof: Optional[str] = None
    status_kind: Optional[str] = None
    language: Optional[str] = None
    color_hex: Optional[str] = None
    folder_name: Optional[str] = None
    exam_weight: Optional[int] = None
    exam_retries: Optional[int] = None
    notes: Optional[str] = None


class Course(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: CourseCode
    full_name: str
    short_name: Optional[str] = None
    module_code: Optional[str] = None
    ects: Optional[int] = None
    prof: Optional[str] = None
    status_kind: Optional[str] = None
    language: Optional[str] = None
    color_hex: Optional[str] = None
    folder_name: Optional[str] = None
    exam_weight: int = 100
    exam_retries: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Schedule slot ----------
class SlotCreate(BaseModel):
    course_code: CourseCode
    kind: SlotKind
    weekday: int = Field(ge=1, le=7)
    start_time: time
    end_time: time
    room: Optional[str] = None
    person: Optional[str] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    notes: Optional[str] = None


class SlotPatch(BaseModel):
    kind: Optional[SlotKind] = None
    weekday: Optional[int] = Field(default=None, ge=1, le=7)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    room: Optional[str] = None
    person: Optional[str] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    notes: Optional[str] = None


class Slot(SlotCreate):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Exam ----------
class ExamPatch(BaseModel):
    scheduled_at: Optional[datetime] = None
    duration_min: Optional[int] = None
    location: Optional[str] = None
    structure: Optional[str] = None
    aids_allowed: Optional[str] = None
    status: Optional[ExamStatus] = None
    weight_pct: Optional[int] = None
    notes: Optional[str] = None


class Exam(BaseModel):
    model_config = ConfigDict(extra="ignore")
    course_code: CourseCode
    scheduled_at: Optional[datetime] = None
    duration_min: Optional[int] = None
    location: Optional[str] = None
    structure: Optional[str] = None
    aids_allowed: Optional[str] = None
    status: ExamStatus = "planned"
    weight_pct: int = 100
    notes: Optional[str] = None


# ---------- Study topic ----------
class StudyTopicCreate(BaseModel):
    course_code: CourseCode
    chapter: Optional[str] = None
    name: str
    description: Optional[str] = None
    kind: Optional[StudyTopicKind] = None
    covered_on: Optional[date] = None
    lecture_id: Optional[str] = None
    status: StudyTopicStatus = "not_started"
    confidence: Optional[int] = Field(default=None, ge=0, le=5)
    notes: Optional[str] = None
    sort_order: int = 0


class StudyTopicPatch(BaseModel):
    chapter: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[StudyTopicKind] = None
    covered_on: Optional[date] = None
    lecture_id: Optional[str] = None
    status: Optional[StudyTopicStatus] = None
    confidence: Optional[int] = Field(default=None, ge=0, le=5)
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class StudyTopic(StudyTopicCreate):
    id: str
    lecture_id: Optional[str] = None
    last_reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Deliverable ----------
class DeliverableCreate(BaseModel):
    course_code: CourseCode
    kind: Optional[DeliverableKind] = None
    name: str
    available_at: Optional[datetime] = None
    due_at: datetime
    status: DeliverableStatus = "open"
    local_path: Optional[str] = None
    external_url: Optional[str] = None
    weight_info: Optional[str] = None
    notes: Optional[str] = None


class DeliverablePatch(BaseModel):
    kind: Optional[DeliverableKind] = None
    name: Optional[str] = None
    available_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    status: Optional[DeliverableStatus] = None
    local_path: Optional[str] = None
    external_url: Optional[str] = None
    weight_info: Optional[str] = None
    notes: Optional[str] = None


class Deliverable(DeliverableCreate):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Task ----------
class TaskCreate(BaseModel):
    course_code: Optional[CourseCode] = None
    title: str
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    status: TaskStatus = "open"
    priority: TaskPriority = "med"
    tags: Optional[List[str]] = None


class TaskPatch(BaseModel):
    course_code: Optional[CourseCode] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    tags: Optional[List[str]] = None


class Task(TaskCreate):
    id: str
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Event ----------
class EventCreate(BaseModel):
    kind: str
    course_code: Optional[CourseCode] = None
    payload: Optional[dict] = None


class Event(EventCreate):
    id: str
    created_at: Optional[datetime] = None


# ---------- Lectures ----------
class LectureCreate(BaseModel):
    course_code: CourseCode
    number: Optional[int] = None
    held_on: Optional[date] = None
    kind: Optional[SlotKind] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    attended: bool = False
    notes: Optional[str] = None


class LecturePatch(BaseModel):
    number: Optional[int] = None
    held_on: Optional[date] = None
    kind: Optional[SlotKind] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    attended: Optional[bool] = None
    notes: Optional[str] = None


class Lecture(LectureCreate):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Dashboard aggregates ----------
class FallBehindItem(BaseModel):
    course_code: CourseCode
    topics: List[StudyTopic]
    last_covered_on: Optional[date]
    next_lecture_at: Optional[datetime]
    severity: FallBehindSeverity


class DashboardSummary(BaseModel):
    now: datetime
    courses: List[Course]
    slots: List[Slot]
    exams: List[Exam]
    deliverables: List[Deliverable]
    tasks: List[Task]
    study_topics: List[StudyTopic]
    lectures: List[Lecture]
    fall_behind: List[FallBehindItem]


# ---------- Auth ----------
class LoginRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None


class SessionInfo(BaseModel):
    authed: bool
    totp_enabled: bool = False


class TotpSetupResponse(BaseModel):
    secret: str            # raw base32 secret to enter manually if QR fails
    provisioning_uri: str  # otpauth:// URI to render as a QR


class TotpVerifyRequest(BaseModel):
    code: str


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------- Bulk lecture helper ----------
class LectureTopicsAdd(BaseModel):
    course_code: CourseCode
    covered_on: date
    kind: StudyTopicKind = "lecture"
    topics: List[dict]  # list of {chapter?, name, status?, sort_order?}
    lecture_id: Optional[str] = None
    create_lecture: Optional[LectureCreate] = None  # if set, create lecture and link topics
