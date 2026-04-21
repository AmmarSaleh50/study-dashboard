/**
 * CYBERPUNK TERMINAL dashboard — ported from docs/examples/study-dashboard-v2.html
 * Renders only when app theme === "terminal". Uses real API data.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { differenceInCalendarDays, parseISO } from "date-fns";
import { useTranslation } from "react-i18next";
import {
  useAppSettings,
  useDashboard,
  useCompleteTask,
  useReopenTask,
} from "@/lib/queries";
import { relative } from "@/lib/time";
import type { CourseCode } from "@/data/types";

function pad(n: number) { return String(n).padStart(2, "0"); }
function courseVar(code: string) { return `var(--course-${code.toLowerCase()})`; }

function progressFor(code: string, topics: { course_code: string; status: string }[]): number {
  const weights: Record<string, number> = {
    not_started: 0, struggling: 0.2, in_progress: 0.5, studied: 0.9, mastered: 1,
  };
  const list = topics.filter((t) => t.course_code === code);
  if (list.length === 0) return 0;
  const total = list.reduce((s, t) => s + (weights[t.status] ?? 0), 0);
  return Math.round((total / list.length) * 100);
}

function severityOf(
  fb: { severity?: string; topics: unknown[] } | undefined,
  okLabel: string,
): { c: string; label: string; op: number } {
  if (!fb || fb.severity === "ok" || fb.topics.length === 0) {
    return { c: "var(--tm-lime)", label: okLabel, op: 0.4 };
  }
  if (fb.severity === "critical") return { c: "var(--tm-magenta)", label: "CRIT", op: 1 };
  return { c: "var(--tm-amber)", label: "WARN", op: 1 };
}

function relLabel(target: Date, now: Date) {
  const diffMs = target.getTime() - now.getTime();
  const m = Math.round(diffMs / 60000);
  const h = Math.round(diffMs / 3600000);
  const d = Math.round(diffMs / 86400000);
  if (m < 0) return { label: "past", sev: "past" as const };
  if (m < 60) return { label: `+${m}m`, sev: "urgent" as const };
  if (h < 24) return { label: `+${h}h`, sev: h < 6 ? ("urgent" as const) : ("soon" as const) };
  if (d === 1) return { label: "+1d", sev: "soon" as const };
  if (d <= 3)  return { label: `+${d}d`, sev: "soon" as const };
  if (d <= 7)  return { label: `+${d}d`, sev: "later" as const };
  return { label: `+${d}d`, sev: "far" as const };
}

function phaseKey(h: number): string {
  if (h < 6)  return "terminal.phase.night";
  if (h < 12) return "terminal.phase.morning";
  if (h < 18) return "terminal.phase.afternoon";
  return "terminal.phase.evening";
}

export function TerminalDashboard() {
  const { t, i18n } = useTranslation();
  const { data, isPending, error } = useDashboard();
  const settings = useAppSettings();

  if (isPending) {
    return (
      <div className="tm-pad">
        <div style={{ padding: 48, color: "var(--tm-muted)" }}>{t("terminal.loading")}</div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="tm-pad">
        <div style={{ padding: 48, color: "var(--tm-magenta)" }}>
          {t("terminal.loadFailed")}
        </div>
      </div>
    );
  }

  const now = parseISO(data.now);
  const displayName = (settings.data?.display_name ?? "").trim() || t("terminal.fallbackName");
  const firstName = displayName.split(" ")[0];
  const semesterLabel = settings.data?.semester_label?.trim() || "";
  const institution = settings.data?.institution?.trim() || "";
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";

  // next event across courses
  const nextEvent = data.fall_behind
    .map((f) =>
      f.next_lecture_at
        ? { code: f.course_code as CourseCode, at: parseISO(f.next_lecture_at) }
        : null
    )
    .filter((x): x is { code: CourseCode; at: Date } => x !== null)
    .sort((a, b) => a.at.getTime() - b.at.getTime())[0];

  const openDeliverables = [...data.deliverables]
    .filter((d) => d.status === "open" || d.status === "in_progress")
    .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime());
  const nextDue = openDeliverables[0];
  const tasksOpen = data.tasks.filter((task) => task.status !== "done" && task.status !== "skipped");

  const progressPerCourse = data.courses.map((c) => progressFor(c.code, data.study_topics));
  const avgProgress = progressPerCourse.length
    ? Math.round(progressPerCourse.reduce((s, v) => s + v, 0) / progressPerCourse.length)
    : 0;
  const totalEcts = data.courses.reduce((s, c) => s + (c.ects ?? 0), 0);

  const behindCourses = data.fall_behind.filter((f) => f.severity !== "ok");
  const behindCount = behindCourses.length;
  const totalBehindTopics = behindCourses.reduce((s, c) => s + c.topics.length, 0);
  const nextUpBehind = nextEvent ? behindCourses.find((b) => b.course_code === nextEvent.code) : undefined;
  const nextUpUnstudied = nextUpBehind?.topics.length ?? 0;

  const subline =
    nextUpUnstudied > 0
      ? t("terminal.unstudiedBefore", { count: nextUpUnstudied, code: nextEvent!.code })
      : behindCount === 0
      ? t("terminal.allClear")
      : null;

  // monday of current week (simple)
  const monday = new Date(now);
  const wd = ((now.getDay() + 6) % 7) + 1; // 1..7
  monday.setDate(now.getDate() - (wd - 1));
  monday.setHours(0, 0, 0, 0);

  const eventsThisWeek = data.slots.filter((s) => s.weekday >= 1 && s.weekday <= 5).length;

  // metrics tone
  const nextDueDays = nextDue ? Math.max(0, differenceInCalendarDays(parseISO(nextDue.due_at), now)) : null;
  const nextDueTone = (() => {
    if (!nextDue) return "default";
    const sev = relative(nextDue.due_at, now).severity;
    return sev === "urgent" ? "critical" : sev === "soon" ? "warn" : "default";
  })();
  const tasksUrgent = tasksOpen.filter((task) => task.priority === "urgent").length;
  const tasksHigh = tasksOpen.filter((task) => task.priority === "high").length;
  const tasksThisWeek = tasksOpen.filter(
    (task) => task.due_at && differenceInCalendarDays(parseISO(task.due_at), now) <= 7
  ).length;

  // session bar next-lecture
  const firstSlot = nextEvent ? relLabel(nextEvent.at, now) : null;

  return (
    <>
      {/* SESSION BAR */}
      <div className="tm-sessbar">
        {semesterLabel && (
          <div className="tm-cell">
            <span>{t("terminal.sem")}</span>
            <b>{semesterLabel}</b>
          </div>
        )}
        <div className="tm-cell">
          <span>{t("terminal.courses")}</span>
          <b>{pad(data.courses.length)}</b>
          <span className="tm-sep">│</span>
          <span>Σ {totalEcts} ECTS</span>
        </div>
        {nextEvent && firstSlot && (
          <div className="tm-cell">
            <span>{t("terminal.next")}</span>
            <b style={{ color: "var(--tm-teal)" }}>{nextEvent.code}</b>
            <span className="tm-sep">│</span>
            <span>{firstSlot.label}</span>
          </div>
        )}
      </div>

      <div className="tm-pad">
        {/* GREETING */}
        <section className="tm-greeting">
          <div>
            <div className="tm-kicker">
              <span className="tm-bar" />
              {t("terminal.session")} · {t(phaseKey(now.getHours()))} · {pad(now.getHours())}:{pad(now.getMinutes())}
            </div>
            <h1>
              {t("terminal.hello")}, <span className="tm-name">{firstName.toLowerCase()}</span>
              <span className="tm-cursor" />
            </h1>
            <div className="tm-subline">
              {nextEvent && firstSlot && (
                <span className="tm-chip">
                  <span className="tm-dot" style={{ background: courseVar(nextEvent.code) }} />
                  {t("terminal.next")} · {nextEvent.code} · <span className="tm-rt">{firstSlot.label}</span>
                </span>
              )}
              {subline && <span>{subline}</span>}
            </div>
          </div>
          <div className="tm-rside">
            <div className="tm-date">
              {now.toLocaleDateString(localeCode, {
                weekday: "short", day: "2-digit", month: "short", year: "numeric",
              }).toUpperCase().replace(/\./g, "")}
            </div>
            <div>
              {semesterLabel}{semesterLabel && institution ? " · " : ""}{institution.toUpperCase()}
            </div>
          </div>
        </section>

        {/* BANNER */}
        {behindCount > 0 && (
          <div className="tm-banner" role="alert">
            <div className="tm-bhead">
              <span className="tm-tag">{t("terminal.alert")}</span>
              <span>{t("terminal.fallBehindDetected")}</span>
              <span className="tm-num">
                {t("terminal.topicsCourses", { count: behindCount, topics: totalBehindTopics })}
              </span>
            </div>
            <div className="tm-bbody">
              <div>
                <h3>
                  {t("terminal.behindOn")}{" "}
                  {behindCourses.slice(0, 3).map((b, i) => (
                    <span key={b.course_code}>
                      <span className="tm-accent">{b.course_code}</span>
                      {i < Math.min(behindCourses.length, 3) - 1 ? " + " : ""}
                    </span>
                  ))}
                  {behindCourses.length > 3 ? " +…" : ""} {t("terminal.beforeNextRun")}
                </h3>
                <ul>
                  {behindCourses.slice(0, 4).map((b) => {
                    const nextIso = b.next_lecture_at
                      ? relLabel(parseISO(b.next_lecture_at), now).label
                      : "—";
                    return (
                      <li key={b.course_code}>
                        <span
                          className={b.severity === "critical" ? "tm-mag" : "tm-amb"}
                        >
                          {b.course_code}
                        </span>{" "}
                        · {b.topics.length} {b.topics.length === 1 ? t("terminal.topic") : t("terminal.topics")} · {t("terminal.nextLecture")}{" "}
                        <b className={b.severity === "critical" ? "tm-mag" : "tm-amb"}>
                          {nextIso}
                        </b>
                      </li>
                    );
                  })}
                </ul>
              </div>
              <div className="tm-sevdots">
                {data.courses.map((c) => {
                  const fb = data.fall_behind.find((f) => f.course_code === c.code);
                  const sev = severityOf(fb, t("common.okShort"));
                  return (
                    <div key={c.code} className="tm-sd">
                      <span
                        className="tm-cd"
                        style={
                          {
                            "--accent": sev.c,
                            "--op": sev.op,
                          } as React.CSSProperties
                        }
                      />
                      <span>{c.code}</span>
                      <span style={{ color: sev.c }}>{sev.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* METRICS */}
        <div className="tm-metrics">
          <div className="tm-tile" data-tone={nextDueTone}>
            <div className="tm-top">
              <span>{t("terminal.tile.nextDeadline")}</span>
              <span className="tm-ic">⧗</span>
            </div>
            <div className="tm-val">
              {nextDue ? (
                <>
                  {nextDueDays ?? 0}
                  <span className="tm-u">{nextDueDays === 1 ? t("terminal.tile.day") : t("terminal.tile.days")}</span>
                </>
              ) : (
                <>—</>
              )}
            </div>
            <div className="tm-hint">
              {nextDue ? `${nextDue.course_code} · ${nextDue.name.toUpperCase()}` : t("terminal.tile.noOpenDeliverables")}
            </div>
          </div>
          <div
            className="tm-tile"
            data-tone={tasksUrgent > 0 ? "critical" : tasksThisWeek > 3 ? "warn" : "default"}
          >
            <div className="tm-top">
              <span>{t("terminal.tile.tasksOpen")}</span>
              <span className="tm-ic">▤</span>
            </div>
            <div className="tm-val">
              {tasksOpen.length}
              <span className="tm-u">{t("terminal.tile.openDoneSplit", { done: data.tasks.length - tasksOpen.length })}</span>
            </div>
            <div className="tm-hint">
              {t("terminal.tile.urgentHigh", { urgent: tasksUrgent, high: tasksHigh })}
            </div>
          </div>
          <div
            className="tm-tile"
            data-tone={avgProgress < 25 ? "warn" : avgProgress >= 70 ? "ok" : "default"}
          >
            <div className="tm-top">
              <span>{t("terminal.tile.avgProgress")}</span>
              <span className="tm-ic">↗</span>
            </div>
            <div className="tm-val">
              {avgProgress}
              <span className="tm-u">{t("terminal.tile.pctEcts", { ects: totalEcts })}</span>
            </div>
            <div className="tm-hint">
              {data.courses
                .map((c, i) => `${c.code} ${pad(progressPerCourse[i] ?? 0)}`)
                .join(" · ")}
            </div>
          </div>
          <div
            className="tm-tile"
            data-tone={behindCount === 0 ? "ok" : behindCourses.some((b) => b.severity === "critical") ? "critical" : "warn"}
          >
            <div className="tm-top">
              <span>{t("terminal.tile.behind")}</span>
              <span className="tm-ic">△</span>
            </div>
            <div className="tm-val">
              {behindCount === 0 ? "✓" : totalBehindTopics}
              <span className="tm-u">
                {behindCount === 0
                  ? t("terminal.tile.onTrack")
                  : t("terminal.tile.topicsCourse", { count: behindCount })}
              </span>
            </div>
            <div className="tm-hint">
              {data.courses
                .map((c) => {
                  const fb = data.fall_behind.find((f) => f.course_code === c.code);
                  return `${c.code} ${fb?.topics.length ?? 0}`;
                })
                .join(" · ")}
            </div>
          </div>
        </div>

        {/* WEEKLY */}
        <div className="tm-section-h">
          <span className="tm-num">§01</span>
          <span className="tm-title">{t("terminal.section.thisWeek")}</span>
          <span className="tm-rule" />
          <span className="tm-meta">
            {t("terminal.section.events", { count: eventsThisWeek })}
          </span>
        </div>
        <TerminalWeekGrid
          slots={data.slots}
          monday={monday}
          now={now}
        />

        {/* COURSES */}
        <div className="tm-section-h">
          <span className="tm-num">§02</span>
          <span className="tm-title">{t("terminal.section.courses")}</span>
          <span className="tm-rule" />
          <span className="tm-meta">
            {t("terminal.section.active", { count: data.courses.length, ects: totalEcts })}
          </span>
        </div>
        <div className="tm-courses">
          {data.courses.map((c, i) => {
            const fb = data.fall_behind.find((f) => f.course_code === c.code);
            const nextL = fb?.next_lecture_at ? relLabel(parseISO(fb.next_lecture_at), now) : null;
            const pct = progressPerCourse[i] ?? 0;
            return (
              <Link
                key={c.code}
                to={`/courses/${c.code}`}
                className="tm-ccard"
                data-idx={`${pad(i + 1)}/${pad(data.courses.length)}`}
                style={{ "--accent": courseVar(c.code) } as React.CSSProperties}
              >
                <div className="tm-head">
                  <span className="tm-ctag">{c.code}</span>
                </div>
                <div className="tm-nm">{c.full_name}</div>
                <div className="tm-cmeta">
                  {c.module_code && <span>{c.module_code}</span>}
                  {c.module_code && c.ects != null && <span className="tm-sep">│</span>}
                  {c.ects != null && <span>{c.ects} ECTS</span>}
                  {c.ects != null && c.language && <span className="tm-sep">│</span>}
                  {c.language && <span>{c.language.slice(0, 2).toUpperCase()}</span>}
                </div>
                {nextL && (
                  <div className="tm-nextl">
                    {t("terminal.courseCard.next")} <span className="tm-rt">{nextL.label}</span>
                  </div>
                )}
                {fb && fb.topics.length > 0 && (
                  <span className="tm-behind">{t("terminal.courseCard.behind", { n: fb.topics.length })}</span>
                )}
                <div className="tm-prog-row">
                  <div className="tm-prog">
                    <div className="tm-f" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="tm-pct">{pad(pct)}%</span>
                </div>
              </Link>
            );
          })}
        </div>

        {/* QUEUE */}
        <div className="tm-section-h">
          <span className="tm-num">§03</span>
          <span className="tm-title">{t("terminal.section.queue")}</span>
          <span className="tm-rule" />
          <span className="tm-meta">{t("terminal.section.queueMeta")}</span>
        </div>
        <div className="tm-twocol">
          <TerminalDeadlines deliverables={openDeliverables} now={now} localeCode={localeCode} />
          <TerminalTasks tasks={data.tasks} now={now} />
        </div>
      </div>
    </>
  );
}

function TerminalWeekGrid({
  slots,
  monday,
  now,
}: {
  slots: { id: string; weekday: number; start_time: string; end_time: string; kind: string; room?: string; course_code: string }[];
  monday: Date;
  now: Date;
}) {
  const { i18n } = useTranslation();
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
  const pxh = 44;
  const sH = 8;
  const toTop = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    return (h + m / 60 - sH) * pxh;
  };
  const toH = (a: string, b: string) => toTop(b) - toTop(a);
  const todayIdx = ((now.getDay() + 6) % 7) + 1; // Mon=1..Sun=7
  const nowTop = toTop(`${pad(now.getHours())}:${pad(now.getMinutes())}`);
  const nowStr = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const nowVisible =
    todayIdx >= 1 && todayIdx <= 5 && now.getHours() >= sH && now.getHours() < sH + hours.length;

  const days = [1, 2, 3, 4, 5].map((i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + (i - 1));
    return {
      i,
      name: d.toLocaleDateString(localeCode, { weekday: "short" }).toUpperCase().replace(/\./g, ""),
      d: `${pad(d.getDate())} ${d.toLocaleDateString(localeCode, { month: "short" }).toUpperCase().replace(/\./g, "")}`,
    };
  });

  const cw = isoWeek(monday);

  return (
    <div className="tm-sched-card">
      <div className="tm-sched">
        <div className="tm-sh tm-corner">
          <div className="tm-dow tm-muted">{i18n.language === "de" ? "KW" : "CW"}{pad(cw)}</div>
          <div className="tm-d-n">{monday.toLocaleDateString(localeCode, { month: "short" }).toUpperCase().replace(/\./g, "")}</div>
        </div>
        {days.map((day) => (
          <div key={day.i} className={"tm-sh" + (day.i === todayIdx ? " tm-today" : "")}>
            <div className="tm-dow">{day.name}</div>
            <div className="tm-d-n">{day.d}</div>
          </div>
        ))}
        <div className="tm-rail" style={{ height: hours.length * pxh }}>
          {hours.map((h) => (
            <div key={h} className="tm-hr" style={{ height: pxh }}>
              <span>{pad(h)}:00</span>
            </div>
          ))}
        </div>
        {days.map((day) => (
          <div
            key={day.i}
            className={"tm-col" + (day.i === todayIdx ? " tm-today" : "")}
            style={{ height: hours.length * pxh }}
          >
            {day.i === todayIdx && nowVisible && (
              <div className="tm-nowline" data-now={nowStr} style={{ top: nowTop }} />
            )}
            {slots
              .filter((s) => s.weekday === day.i)
              .map((s) => (
                <div
                  key={s.id}
                  className="tm-blk"
                  style={
                    {
                      top: toTop(s.start_time.slice(0, 5)),
                      height: toH(s.start_time.slice(0, 5), s.end_time.slice(0, 5)),
                      "--accent": courseVar(s.course_code),
                    } as React.CSSProperties
                  }
                >
                  <div className="tm-tm">{s.start_time.slice(0, 5)}</div>
                  <div className="tm-pc">
                    {s.course_code}{" "}
                    <span className="tm-kind">{s.kind}</span>
                  </div>
                  {s.room && <div className="tm-rm">▸ {s.room}</div>}
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function TerminalDeadlines({
  deliverables,
  now,
  localeCode,
}: {
  deliverables: { id: string; course_code: string; kind: string; name: string; due_at: string; status: string }[];
  now: Date;
  localeCode: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="tm-pnl">
      <div className="tm-phead">
        <span className="tm-title">{t("terminal.panel.deadlines")}</span>
        <span>{t("terminal.panel.next3wks")}</span>
        <span className="tm-n">N={deliverables.length}</span>
      </div>
      {deliverables.length === 0 && (
        <div style={{ padding: 20, color: "var(--tm-muted)", fontSize: 11, letterSpacing: "0.1em" }}>
          {t("terminal.panel.noOpen")}
        </div>
      )}
      {deliverables.slice(0, 10).map((d) => {
        const rt = relLabel(parseISO(d.due_at), now);
        const dt = new Date(d.due_at);
        const abs = `${pad(dt.getDate())} ${dt.toLocaleDateString(localeCode, { month: "short" }).toUpperCase().replace(/\./g, "")} · ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
        return (
          <div
            key={d.id}
            className="tm-row"
            style={{ "--accent": courseVar(d.course_code) } as React.CSSProperties}
            onClick={() => navigate(`/courses/${d.course_code}`)}
          >
            <span className="tm-ct">{d.course_code}</span>
            <div style={{ minWidth: 0 }}>
              <div className="tm-nm">{d.name}</div>
              <div className="tm-sub">
                {d.kind} · {abs}
              </div>
            </div>
            <span className="tm-stat" data-s={d.status}>
              {t(`kinds.status.${d.status}`, d.status.replace("_", " "))}
            </span>
            <span className="tm-rt" data-sev={rt.sev}>{rt.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function TerminalTasks({
  tasks,
  now,
}: {
  tasks: { id: string; course_code?: string | null; title: string; due_at?: string | null; status: string }[];
  now: Date;
}) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const complete = useCompleteTask();
  const reopen = useReopenTask();
  void pending;

  async function toggle(id: string, isDone: boolean) {
    setPending((s) => ({ ...s, [id]: true }));
    try {
      if (isDone) await reopen.mutateAsync(id);
      else await complete.mutateAsync(id);
    } finally {
      setPending((s) => {
        const next = { ...s };
        delete next[id];
        return next;
      });
    }
  }

  const visible = tasks.slice(0, 12);
  return (
    <div className="tm-pnl">
      <div className="tm-phead">
        <span className="tm-title">{t("terminal.panel.taskInbox")}</span>
        <span>{t("terminal.panel.thisWeek")}</span>
        <span className="tm-n">
          N={tasks.filter((task) => task.status !== "done" && task.status !== "skipped").length}
        </span>
      </div>
      {visible.length === 0 && (
        <div style={{ padding: 20, color: "var(--tm-muted)", fontSize: 11, letterSpacing: "0.1em" }}>
          {t("terminal.panel.noTasks")}
        </div>
      )}
      {visible.map((task) => {
        const isDone = task.status === "done" || task.status === "skipped";
        const rt = task.due_at ? relLabel(parseISO(task.due_at), now) : null;
        return (
          <div
            key={task.id}
            className="tm-row tm-task"
            style={
              {
                "--accent": task.course_code ? courseVar(task.course_code) : "var(--tm-muted)",
                opacity: isDone ? 0.5 : 1,
              } as React.CSSProperties
            }
          >
            <span
              className="tm-chk"
              data-c={isDone}
              onClick={() => toggle(task.id, isDone)}
              role="checkbox"
              aria-checked={isDone}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="var(--tm-bg)" strokeWidth="3" strokeLinecap="square">
                <path d="M4 12l5 5L20 6" />
              </svg>
            </span>
            <span className="tm-ct">{task.course_code ?? "—"}</span>
            <div style={{ minWidth: 0 }}>
              <div
                className="tm-nm"
                style={{ textDecoration: isDone ? "line-through" : "none" }}
              >
                {task.title}
              </div>
            </div>
            <span className="tm-stat" data-s={isDone ? "done" : task.status}>
              {t(`kinds.status.${isDone ? "done" : task.status}`, (isDone ? "done" : task.status).replace("_", " "))}
            </span>
            {rt && (
              <span className="tm-rt" data-sev={rt.sev}>
                {rt.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}
