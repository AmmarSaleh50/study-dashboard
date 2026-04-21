/**
 * SWISS GRID dashboard — ported from docs/examples/study-dashboard-v6.html.
 * Active when theme === "swiss". Uses real API data. Omits invented design
 * flair: "№ 04" issue number, "Vol. II", weather tile, sidebar footer.
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
import type { CourseCode } from "@/data/types";

function pad(n: number) { return String(n).padStart(2, "0"); }
function cv(code: string) { return `var(--course-${code.toLowerCase()})`; }

function progressFor(code: string, topics: { course_code: string; status: string }[]): number {
  const weights: Record<string, number> = {
    not_started: 0, struggling: 0.2, in_progress: 0.5, studied: 0.9, mastered: 1,
  };
  const list = topics.filter((t) => t.course_code === code);
  if (list.length === 0) return 0;
  const total = list.reduce((s, t) => s + (weights[t.status] ?? 0), 0);
  return Math.round((total / list.length) * 100);
}

function relLabel(target: Date, now: Date) {
  const diffMs = target.getTime() - now.getTime();
  const m = Math.round(diffMs / 60000);
  const h = Math.round(diffMs / 3600000);
  const d = Math.round(diffMs / 86400000);
  if (m < 0) return { label: "—", sev: "past" as const };
  if (m < 60) return { label: `+${m}m`, sev: "urgent" as const };
  if (h < 24) return { label: `+${h}h`, sev: h < 6 ? ("urgent" as const) : ("soon" as const) };
  if (d <= 3) return { label: `+${d}d`, sev: "soon" as const };
  return { label: `+${d}d`, sev: "later" as const };
}

export function SwissDashboard() {
  const { t, i18n } = useTranslation();
  const { data, isPending, error } = useDashboard();
  const settings = useAppSettings();

  if (isPending) {
    return <div className="s-page"><div style={{ gridColumn: "1 / -1" }}>{t("swiss.loading")}</div></div>;
  }
  if (error || !data) {
    return <div className="s-page"><div style={{ gridColumn: "1 / -1", color: "var(--s-red)" }}>{t("swiss.loadFailed")}</div></div>;
  }

  const now = parseISO(data.now);
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const displayName = (settings.data?.display_name ?? "").trim() || t("swiss.fallbackName");
  void displayName;
  const semesterLabel = settings.data?.semester_label?.trim() || "";
  const institution = settings.data?.institution?.trim() || "";

  const nextEvent = data.fall_behind
    .map((f) => f.next_lecture_at
      ? { code: f.course_code as CourseCode, at: parseISO(f.next_lecture_at) }
      : null)
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

  const monday = new Date(now);
  const wd = ((now.getDay() + 6) % 7) + 1;
  monday.setDate(now.getDate() - (wd - 1));
  monday.setHours(0, 0, 0, 0);

  const eventsThisWeek = data.slots.filter((s) => s.weekday >= 1 && s.weekday <= 5).length;
  const firstSlot = nextEvent ? relLabel(nextEvent.at, now) : null;
  const semWeek = semesterWeek(now, settings.data?.semester_start);
  const cw = semWeek ?? isoWeek(monday);

  const nextDueDays = nextDue ? Math.max(0, differenceInCalendarDays(parseISO(nextDue.due_at), now)) : null;
  const tasksUrgent = tasksOpen.filter((task) => task.priority === "urgent").length;
  const tasksHigh = tasksOpen.filter((task) => task.priority === "high").length;
  const tasksThisWeek = tasksOpen.filter(
    (task) => task.due_at && differenceInCalendarDays(parseISO(task.due_at), now) <= 7
  ).length;

  const dateShort = now.toLocaleDateString(localeCode, { weekday: "short", day: "2-digit", month: "short" });
  const hhmm = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const relInTime = firstSlot ? t("swiss.inRel", { rel: firstSlot.label.replace("+", "") }) : "";

  return (
    <div className="s-page">
      {/* MASTHEAD */}
      <header className="s-mast">
        <div className="s-m-left">
          {semesterLabel && <div className="s-hsub">{semesterLabel}</div>}
        </div>
        <div className="s-m-right">
          {institution && <div>{institution}</div>}
          <div>{t("swiss.wk")} <b>{pad(cw)}</b></div>
        </div>
      </header>

      {/* HEADLINE */}
      <section className="s-headline">
        <div className="s-kicker">
          <span>{dateShort}</span>
          <span>{t("swiss.morningBriefing")}</span>
          <span>{hhmm}</span>
        </div>
        <h1>
          {behindCount > 0 ? (
            <>
              {t("swiss.youAre")} <em>{t("swiss.topicsBehind", { count: totalBehindTopics })}</em>
              {firstSlot && <>, {t("swiss.andNextLecture")} <em>{relInTime}</em></>}.
            </>
          ) : (
            <>{t("swiss.allCaughtPre")} {firstSlot ? <em>{relInTime}</em> : t("swiss.notScheduled")}.</>
          )}
        </h1>
        {behindCount > 0 ? (
          <p className="s-lede">
            {t("swiss.ledePre", { count: behindCount })}
            {behindCourses.slice(0, 3).map((b, i, arr) => (
              <span key={b.course_code}>
                <b>{b.course_code}</b> ({b.topics.length}){i < arr.length - 1 ? ` ${t("swiss.ledeAnd")} ` : ""}
              </span>
            ))}
            {t("swiss.ledeTail")}
          </p>
        ) : (
          <p className="s-lede">
            {t("swiss.ledeClear")}
          </p>
        )}
        {nextEvent && firstSlot && (
          <div className="s-next">
            <span>{t("swiss.next")}</span>
            <b>{nextEvent.code}</b>
            <span>{pad(nextEvent.at.getHours())}:{pad(nextEvent.at.getMinutes())}</span>
            <span className="s-rt">{firstSlot.label}</span>
          </div>
        )}
      </section>

      {/* NOTICE */}
      {behindCount > 0 && (
        <section className="s-notice">
          <div className="s-nl"><div className="s-num">01 / {t("swiss.notice")}</div></div>
          <h2 className="s-title">
            {t("swiss.noticeHeadlinePre", { count: totalBehindTopics, topics: totalBehindTopics })} <em>{t("swiss.overdue")}</em> {t("swiss.noticeHeadlineMid")}{" "}
            {t("swiss.noticeHeadlineMidCount", { count: behindCount })}{" "}
            <b>{t("swiss.noticeHeadlineEnd")}</b>.
          </h2>
          <div className="s-list">
            {data.courses.map((c, i) => {
              const fb = data.fall_behind.find((f) => f.course_code === c.code);
              const ok = !fb || fb.severity === "ok" || fb.topics.length === 0;
              const rt = fb?.next_lecture_at ? relLabel(parseISO(fb.next_lecture_at), now) : null;
              return (
                <div key={c.code} className="s-r">
                  <span className="s-i">{pad(i + 1)}</span>
                  <span className="s-c">{c.code}</span>
                  <span>
                    {ok
                      ? t("swiss.onSchedule")
                      : t("swiss.topics", { count: fb!.topics.length })}
                  </span>
                  {ok ? (
                    <span className="s-ok">{t("swiss.ok")}</span>
                  ) : (
                    <span className="s-rr">{rt?.label ?? "—"}</span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* STATS */}
      <div className="s-sh">
        <div className="s-n">{behindCount > 0 ? `02 / ${t("swiss.stats")}` : `01 / ${t("swiss.stats")}`}</div>
        <div className="s-t">{t("swiss.vitalSigns")} <em>{t("swiss.vitalSignsSub")}</em></div>
        <div className="s-meta">{t("swiss.asOf", { time: hhmm })}</div>
      </div>
      <div className="s-c-3 s-st" data-tone={nextDueDays !== null && nextDueDays <= 1 ? "hot" : nextDueDays !== null && nextDueDays <= 3 ? "warn" : "default"}>
        <div className="s-l"><span>{t("swiss.tile.nextDeadline")}</span><span className="s-ix">01</span></div>
        <div className="s-v">
          {nextDue ? <>{nextDueDays ?? 0}<span className="s-u">{nextDueDays === 1 ? t("swiss.tile.day") : t("swiss.tile.days")}</span></> : "—"}
        </div>
        <div className="s-h">
          {nextDue ? `${nextDue.course_code} — ${nextDue.name}.` : t("swiss.tile.noOpenDeliverables")}
        </div>
      </div>
      <div className="s-c-3 s-st" data-tone={tasksUrgent > 0 ? "hot" : tasksThisWeek > 3 ? "warn" : "default"}>
        <div className="s-l"><span>{t("swiss.tile.tasksOpen")}</span><span className="s-ix">02</span></div>
        <div className="s-v">{tasksOpen.length}<span className="s-u">/ {data.tasks.length}</span></div>
        <div className="s-h">{t("swiss.tile.urgentHigh", { urgent: tasksUrgent, high: tasksHigh })}</div>
      </div>
      <div className="s-c-3 s-st" data-tone={avgProgress >= 70 ? "ok" : avgProgress < 25 ? "warn" : "default"}>
        <div className="s-l"><span>{t("swiss.tile.meanProgress")}</span><span className="s-ix">03</span></div>
        <div className="s-v">{avgProgress}<span className="s-u">%</span></div>
        <div className="s-h">
          {data.courses.map((c, i) => `${c.code} ${pad(progressPerCourse[i] ?? 0)}`).join(" · ")}
        </div>
      </div>
      <div className="s-c-3 s-st" data-tone={behindCount === 0 ? "ok" : behindCourses.some((b) => b.severity === "critical") ? "hot" : "warn"}>
        <div className="s-l"><span>{t("swiss.tile.inArrears")}</span><span className="s-ix">04</span></div>
        <div className="s-v">
          {behindCount === 0 ? t("swiss.tile.nil") : `−${totalBehindTopics}`}
          <span className="s-u">{behindCount === 0 ? "" : t("swiss.tile.topics")}</span>
        </div>
        <div className="s-h">
          {behindCount === 0
            ? t("swiss.tile.everyOnSchedule")
            : t("swiss.tile.acrossCourses", { count: behindCount })}
        </div>
      </div>

      {/* SCHEDULE */}
      <div className="s-sh">
        <div className="s-n">{behindCount > 0 ? `03 / ${t("swiss.schedule")}` : `02 / ${t("swiss.schedule")}`}</div>
        <div className="s-t">{t("swiss.weekOverview")} <em>{t("swiss.weekOverviewSub")}</em></div>
        <div className="s-meta">{t("swiss.engagements", { count: eventsThisWeek })}</div>
      </div>
      <div className="s-c-12">
        <SwissSchedule slots={data.slots} monday={monday} now={now} localeCode={localeCode} />
      </div>

      {/* COURSES */}
      <div className="s-sh">
        <div className="s-n">{behindCount > 0 ? `04 / ${t("swiss.courses")}` : `03 / ${t("swiss.courses")}`}</div>
        <div className="s-t">{t("swiss.index")} <em>{t("swiss.indexSub", { count: data.courses.length })}</em></div>
        <div className="s-meta">{t("swiss.ectsTotal", { ects: totalEcts })}</div>
      </div>
      {data.courses.map((c, i) => {
        const fb = data.fall_behind.find((f) => f.course_code === c.code);
        const nextL = fb?.next_lecture_at ? relLabel(parseISO(fb.next_lecture_at), now) : null;
        const pct = progressPerCourse[i] ?? 0;
        const behind = fb?.topics.length ?? 0;
        return (
          <Link
            key={c.code}
            to={`/courses/${c.code}`}
            className="s-c-3 s-course-card"
            style={{ "--accent": cv(c.code) } as React.CSSProperties}
          >
            <div className="s-idx-line">
              <span className="s-ix">{pad(i + 1)} / {pad(data.courses.length)}</span>
              <span>
                {c.language?.slice(0, 2).toUpperCase() ?? ""}
                {c.ects != null && ` · ${c.ects} ECTS`}
              </span>
            </div>
            <div className="s-ccode">{c.code}<span className="s-dot" /></div>
            <div className="s-cfull">{c.full_name}</div>
            {behind > 0 && <div className="s-beh">{t("swiss.behindN", { n: behind })}</div>}
            <div className="s-cmeta">
              {c.module_code && <><span>{t("swiss.module")}</span><b>{c.module_code}</b></>}
              {nextL && <><span>{t("swiss.next")}</span><b>{nextL.label}</b></>}
            </div>
            <div className="s-cprog">
              <div className="s-bar">
                <div className="s-f" style={{ "--w": `${pct}%` } as React.CSSProperties} />
              </div>
              <div className="s-pct">{pad(pct)}%</div>
            </div>
          </Link>
        );
      })}

      {/* QUEUES */}
      <div className="s-sh">
        <div className="s-n">{behindCount > 0 ? `05 / ${t("swiss.queues")}` : `04 / ${t("swiss.queues")}`}</div>
        <div className="s-t">{t("swiss.deadlinesHeading")} <em>{t("swiss.deadlinesHeadingSub")}</em></div>
        <div className="s-meta">{t("swiss.deadlinesMeta", { dl: openDeliverables.length, open: tasksOpen.length })}</div>
      </div>
      <SwissDeadlines deliverables={openDeliverables} now={now} />
      <SwissTasks tasks={data.tasks} now={now} />
    </div>
  );
}

function SwissSchedule({
  slots, monday, now, localeCode,
}: {
  slots: { id: string; weekday: number; start_time: string; end_time: string; kind: string; room?: string; course_code: string }[];
  monday: Date;
  now: Date;
  localeCode: string;
}) {
  const { t } = useTranslation();
  const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
  const pxh = 48;
  const sH = 8;
  const toTop = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    return (h + m / 60 - sH) * pxh;
  };
  const toH = (a: string, b: string) => toTop(b) - toTop(a);
  const todayIdx = ((now.getDay() + 6) % 7) + 1;
  const nowTop = toTop(`${pad(now.getHours())}:${pad(now.getMinutes())}`);
  const nowStr = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const nowVisible =
    todayIdx >= 1 && todayIdx <= 5 &&
    now.getHours() >= sH && now.getHours() < sH + hours.length;

  const cw = isoWeek(monday);
  const days = [1, 2, 3, 4, 5].map((i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + (i - 1));
    return {
      i,
      name: d.toLocaleDateString(localeCode, { weekday: "long" }),
      d: `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`,
    };
  });

  return (
    <div className="s-sched">
      <div className="s-sched-grid">
        <div className="s-shd-th">
          <div className="s-d" style={{ fontSize: 12, color: "var(--s-ink-3)" }}>{t("swiss.wk")} {pad(cw)}</div>
        </div>
        {days.map((day) => (
          <div key={day.i} className={"s-shd-th" + (day.i === todayIdx ? " s-today" : "")}>
            <div className="s-d">{day.name}</div>
            <div className="s-n">{day.d}</div>
          </div>
        ))}
        <div className="s-shd-rail" style={{ height: hours.length * pxh }}>
          {hours.map((h) => (
            <div key={h} className="s-h" style={{ height: pxh }}>{pad(h)}:00</div>
          ))}
        </div>
        {days.map((day) => (
          <div key={day.i}
            className={"s-shd-col" + (day.i === todayIdx ? " s-today" : "")}
            style={{ height: hours.length * pxh }}>
            {day.i === todayIdx && nowVisible && (
              <div className="s-nowline" data-t={nowStr} style={{ top: nowTop }} />
            )}
            {slots
              .filter((s) => s.weekday === day.i)
              .map((s) => (
                <div key={s.id}
                  className="s-evt"
                  style={{
                    top: toTop(s.start_time.slice(0, 5)),
                    height: toH(s.start_time.slice(0, 5), s.end_time.slice(0, 5)) - 2,
                    "--accent": cv(s.course_code),
                  } as React.CSSProperties}>
                  <div className="s-tm">{s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}</div>
                  <div className="s-tt"><span className="s-cc">{s.course_code}</span> / {s.kind}</div>
                  {s.room && <div className="s-rr">{s.room}</div>}
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function SwissDeadlines({
  deliverables, now,
}: {
  deliverables: { id: string; course_code: string; kind: string; name: string; due_at: string; status: string }[];
  now: Date;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="s-c-7 s-list-wrap">
      <div className="s-lh">
        <span className="s-ti">{t("swiss.deadlinesTitle")}</span>
        <span>{t("swiss.deadlinesN", { n: pad(deliverables.length) })}</span>
      </div>
      {deliverables.length === 0 && (
        <div style={{ padding: "14px 0", color: "var(--s-ink-3)", fontSize: 13 }}>{t("swiss.nothingOpen")}</div>
      )}
      {deliverables.slice(0, 10).map((d, i) => {
        const rt = relLabel(parseISO(d.due_at), now);
        const dt = new Date(d.due_at);
        const abs = `${pad(dt.getDate())}.${pad(dt.getMonth() + 1)} · ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
        return (
          <div key={d.id} className="s-lr"
            style={{ "--accent": cv(d.course_code) } as React.CSSProperties}
            onClick={() => navigate(`/courses/${d.course_code}`)}>
            <span className="s-num">{pad(i + 1)}</span>
            <span className="s-cc">{d.course_code}</span>
            <div style={{ minWidth: 0 }}>
              <div className="s-nm">{d.name}</div>
              <div className="s-sub">{d.kind} · {abs}</div>
            </div>
            <span className="s-st" data-s={d.status}>{t(`kinds.status.${d.status}`, d.status.replace("_", " "))}</span>
            <span className="s-rt" data-sev={rt.sev}>{rt.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function SwissTasks({
  tasks, now,
}: {
  tasks: { id: string; course_code?: string | null; title: string; due_at?: string | null; status: string }[];
  now: Date;
}) {
  const { t } = useTranslation();
  const [, setPending] = useState<Record<string, boolean>>({});
  const complete = useCompleteTask();
  const reopen = useReopenTask();

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

  const openCount = tasks.filter((task) => task.status !== "done" && task.status !== "skipped").length;
  const visible = tasks.slice(0, 12);

  return (
    <div className="s-c-5 s-list-wrap">
      <div className="s-lh">
        <span className="s-ti">{t("swiss.todayWeek")}</span>
        <span>{t("swiss.nOpen", { n: pad(openCount) })}</span>
      </div>
      {visible.length === 0 && (
        <div style={{ padding: "14px 0", color: "var(--s-ink-3)", fontSize: 13 }}>{t("swiss.noTasks")}</div>
      )}
      {visible.map((task, i) => {
        const isDone = task.status === "done" || task.status === "skipped";
        const rt = task.due_at ? relLabel(parseISO(task.due_at), now) : null;
        return (
          <div key={task.id} className="s-tr"
            style={{
              "--accent": task.course_code ? cv(task.course_code) : "var(--s-ink-3)",
              opacity: isDone ? 0.5 : 1,
            } as React.CSSProperties}>
            <span className="s-chk" data-on={isDone} onClick={() => toggle(task.id, isDone)} />
            <span
              style={{
                fontFamily: "var(--s-font-mono)",
                fontSize: 11,
                color: "var(--s-ink-3)",
                textAlign: "right",
                letterSpacing: "0.04em",
              }}
            >
              {pad(i + 1)}
            </span>
            <span
              style={{
                fontFamily: "var(--s-font-mono)",
                fontSize: 11,
                fontWeight: 600,
                color: "var(--accent)",
                borderLeft: "3px solid var(--accent)",
                paddingLeft: 8,
                letterSpacing: "0.04em",
              }}
            >
              {task.course_code ?? "—"}
            </span>
            <div style={{
              fontWeight: 500,
              fontSize: 14,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              textDecoration: isDone ? "line-through" : "none",
              color: "var(--s-ink)",
            }}>
              {task.title}
            </div>
            {rt && (
              <span
                style={{
                  fontFamily: "var(--s-font-mono)",
                  fontSize: 12,
                  fontWeight: 600,
                  textAlign: "right",
                  color:
                    rt.sev === "urgent" ? "var(--s-red)"
                      : rt.sev === "soon" ? "var(--s-ink)"
                        : "var(--s-ink-3)",
                }}
              >
                {rt.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function semesterWeek(now: Date, startIso: string | null | undefined): number | null {
  if (!startIso) return null;
  const start = new Date(startIso + "T00:00:00");
  const ms = now.getTime() - start.getTime();
  if (ms < 0) return 0;
  return Math.floor(ms / (7 * 24 * 60 * 60 * 1000)) + 1;
}

function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}
