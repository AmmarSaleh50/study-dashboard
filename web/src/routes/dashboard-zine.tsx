/**
 * PASTEL ZINE dashboard — ported from docs/examples/study-dashboard-v3.html.
 * Renders when app theme === "zine". Uses real API data. Invented
 * flavor from the design file (weather line, issue number, price tag,
 * pull-quote) is intentionally omitted — we only surface fields we
 * actually have.
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
  if (m < 0)  return { label: "past",   sev: "past"   as const };
  if (m < 60) return { label: `+${m}m`, sev: "urgent" as const };
  if (h < 24) return { label: `+${h}h`, sev: h < 6 ? ("urgent" as const) : ("soon" as const) };
  if (d <= 3) return { label: `+${d}d`, sev: "soon"   as const };
  return         { label: `+${d}d`, sev: "later"  as const };
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function ZineDashboard() {
  const { t, i18n } = useTranslation();
  const { data, isPending, error } = useDashboard();
  const settings = useAppSettings();

  if (isPending) {
    return <div className="z-app"><div style={{ padding: 48 }}>{t("common.loading")}</div></div>;
  }
  if (error || !data) {
    return <div className="z-app"><div style={{ padding: 48, color: "var(--z-pink-2)" }}>{t("dashboard.loadFailed")}</div></div>;
  }

  const now = parseISO(data.now);
  const displayName = (settings.data?.display_name ?? "").trim() || "you";
  const firstName = displayName.split(" ")[0];
  const institution = settings.data?.institution?.trim() || "";
  const semesterLabel = settings.data?.semester_label?.trim() || "";

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
  const tasksOpen = data.tasks.filter((t) => t.status !== "done" && t.status !== "skipped");

  const progressPerCourse = data.courses.map((c) => progressFor(c.code, data.study_topics));
  const avgProgress = progressPerCourse.length
    ? Math.round(progressPerCourse.reduce((s, v) => s + v, 0) / progressPerCourse.length)
    : 0;
  const totalEcts = data.courses.reduce((s, c) => s + (c.ects ?? 0), 0);

  const behindCourses = data.fall_behind.filter((f) => f.severity !== "ok");
  const behindCount = behindCourses.length;
  const totalBehindTopics = behindCourses.reduce((s, c) => s + c.topics.length, 0);

  // monday of the current week
  const monday = new Date(now);
  const wd = ((now.getDay() + 6) % 7) + 1;
  monday.setDate(now.getDate() - (wd - 1));
  monday.setHours(0, 0, 0, 0);
  const eventsThisWeek = data.slots.filter((s) => s.weekday >= 1 && s.weekday <= 5).length;

  const nextDueDays = nextDue ? Math.max(0, differenceInCalendarDays(parseISO(nextDue.due_at), now)) : null;
  const tasksUrgent = tasksOpen.filter((t) => t.priority === "urgent").length;
  const tasksHigh = tasksOpen.filter((t) => t.priority === "high").length;
  const tasksThisWeek = tasksOpen.filter(
    (t) => t.due_at && differenceInCalendarDays(parseISO(t.due_at), now) <= 7
  ).length;

  const firstSlot = nextEvent ? relLabel(nextEvent.at, now) : null;
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const dateStr = now.toLocaleDateString(localeCode, {
    weekday: "short", day: "2-digit", month: "short", year: "numeric",
  }).toUpperCase();

  return (
    <div className="z-app">
      {/* MASTHEAD */}
      <div className="z-masthead">
        <div className="z-logo">
          <div className="z-mark">{initials(displayName)}</div>
          <div className="z-words">
            {firstName.toUpperCase()}<br />{t("zine.youStudyDashboard")}
            {institution && <small>{institution}</small>}
          </div>
        </div>
        {semesterLabel && (
          <div className="z-issue">
            <span className="z-big">{semesterLabel.toUpperCase()}</span>
          </div>
        )}
        <div className="z-meta">
          <div>{dateStr}</div>
          <div>{pad(now.getHours())}:{pad(now.getMinutes())}</div>
        </div>
      </div>

      <div className="z-runstrip">
        <span><span className="z-star">✦</span> {t("zine.coursesRunstrip", { count: data.courses.length })}</span>
        <span>Σ {totalEcts} ECTS</span>
        {nextEvent && firstSlot && (
          <span>{t("zine.nextRunstrip")} {nextEvent.code} · {firstSlot.label}</span>
        )}
      </div>

      {/* HELLO */}
      <section className="z-hello">
        <div className="z-kicker">{t("zine.heyYou")}</div>
        <h1>
          {t("zine.hi")}, <span className="z-name">{firstName.toLowerCase()}</span><span className="z-bang">!</span>
          <svg className="z-scribble" viewBox="0 0 200 80" fill="none" stroke="#ff4f92" strokeWidth="3" strokeLinecap="round">
            <path d="M10 40 Q 40 10, 70 35 T 130 30 T 190 45" />
          </svg>
        </h1>
        <div className="z-underh1">
          {nextEvent && firstSlot && (
            <span className="z-nextchip">
              <span className="z-dot" />
              {t("zine.nextUp")}&nbsp;·&nbsp;{nextEvent.code}&nbsp;·&nbsp;<span className="z-rt">{firstSlot.label}</span>
            </span>
          )}
          {behindCount > 0 && (
            <span>
              <b>
                {totalBehindTopics} {totalBehindTopics === 1 ? t("common.topic", "topic") : t("common.topics", "topics")}
              </b>{" "}
              {t("zine.unstudiedAcrossLead", "unstudied across")}{" "}
              <b>
                {behindCount} {behindCount === 1 ? t("common.course", "course") : t("common.courses", "courses")}
              </b>{" "}
              — {t("zine.triageTail", "triage what matters, skip the rest.")}
            </span>
          )}
          <span className="z-todayis">{dateStr} · {pad(now.getHours())}:{pad(now.getMinutes())}</span>
        </div>
      </section>

      {/* SECTION 01 — THE SITUATION */}
      <section className="z-sec">
        <div className="z-sec-h">
          <div className="z-num" data-c="yellow">01</div>
          <div className="z-title-wrap">
            <h2>{t("zine.situationTitle")}</h2>
            <div className="z-sub">{t("zine.situationSub")}</div>
          </div>
          <div className="z-meta">{t("zine.situationMeta")}</div>
        </div>

        {behindCount > 0 && (
          <div className="z-behind" role="alert">
            <div className="z-behind-grid">
              <div>
                <h3>
                  {t("zine.noticeOfArrearsPre", "You're")} <u>{t("courseDetail.fallBehind.title").toLowerCase()}</u>{" "}
                  {t("zine.noticeOfArrearsOn", "on")} {totalBehindTopics}{" "}
                  {totalBehindTopics === 1 ? t("common.topic", "topic") : t("common.topics", "topics")}{" "}
                  {t("zine.noticeOfArrearsAcross", "across")} {behindCount}{" "}
                  {behindCount === 1 ? t("common.course", "course") : t("common.courses", "courses")}{" "}
                  {t("zine.noticeOfArrearsBefore", "before this week's lectures.")}
                </h3>
                <ul>
                  {behindCourses.slice(0, 3).map((b) => {
                    const nextStr = b.next_lecture_at
                      ? relLabel(parseISO(b.next_lecture_at), now).label
                      : "—";
                    return (
                      <li key={b.course_code}>
                        <b>{b.course_code}</b> — {b.topics.length}{" "}
                        {b.topics.length === 1 ? t("common.topic", "topic") : t("common.topics", "topics")}{" "}
                        · {t("zine.nextLecture")} <b>{nextStr}</b>
                      </li>
                    );
                  })}
                </ul>
              </div>
              <div className="z-sevwrap">
                {data.courses.map((c) => {
                  const fb = data.fall_behind.find((f) => f.course_code === c.code);
                  const ok = !fb || fb.severity === "ok" || fb.topics.length === 0;
                  const label = ok ? "OK" : `${fb!.topics.length}!`;
                  return (
                    <div key={c.code} className="z-sev">
                      <span
                        className="z-badge"
                        style={{ "--accent": cv(c.code) } as React.CSSProperties}
                        data-state={ok ? "ok" : "hot"}
                      >
                        {label}
                      </span>
                      <span className="z-lbl">{c.code}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div style={{ height: 16 }} />

        <div className="z-tiles">
          <div className="z-tile" data-tone={nextDueDays !== null && nextDueDays <= 1 ? "critical" : nextDueDays !== null && nextDueDays <= 3 ? "warn" : "default"}>
            {nextDueDays !== null && nextDueDays <= 1 && <span className="z-sticker">{t("zine.tile.actNow")}</span>}
            <div className="z-ico">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
            </div>
            <div className="z-lbl">{t("zine.tile.nextDeadline")}</div>
            <div className="z-val">
              {nextDue ? (
                <>
                  {nextDueDays ?? 0}
                  <span className="z-u">
                    {t(nextDueDays === 1 ? "zine.tile.day" : "zine.tile.days")}
                  </span>
                </>
              ) : "—"}
            </div>
            <div className="z-hint">
              {nextDue ? `${nextDue.course_code} · ${nextDue.name}` : t("zine.tile.nothingOpen")}
            </div>
          </div>

          <div className="z-tile" data-tone={tasksUrgent > 0 ? "critical" : tasksThisWeek > 3 ? "warn" : "default"}>
            <div className="z-ico">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 6h16M4 12h16M4 18h10" />
                <circle cx="19" cy="18" r="2" fill="currentColor" />
              </svg>
            </div>
            <div className="z-lbl">{t("zine.tile.tasksOpen")}</div>
            <div className="z-val">{tasksOpen.length}<span className="z-u">{t("common.open").toLowerCase()}</span></div>
            <div className="z-hint">
              {t("dashboard.tile.urgent", { n: tasksUrgent })} · {t("dashboard.tile.high", { n: tasksHigh })} · {data.tasks.length - tasksOpen.length} {t("common.done")}
            </div>
          </div>

          <div className="z-tile" data-tone={avgProgress >= 70 ? "ok" : avgProgress < 25 ? "warn" : "default"}>
            <div className="z-ico">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 17l6-6 4 4 8-9" />
                <path d="M14 6h7v7" />
              </svg>
            </div>
            <div className="z-lbl">{t("zine.tile.avgProgress")}</div>
            <div className="z-val">{avgProgress}<span className="z-u">%</span></div>
            <div className="z-hint">
              {data.courses.map((c, i) => `${c.code} ${progressPerCourse[i] ?? 0}`).join(" · ")}
            </div>
          </div>

          <div className="z-tile" data-tone={behindCount === 0 ? "ok" : behindCourses.some((b) => b.severity === "critical") ? "critical" : "warn"}>
            {behindCourses.some((b) => b.severity === "critical") && <span className="z-sticker">{t("zine.tile.hot")}</span>}
            <div className="z-ico">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3s4 4 4 8a4 4 0 0 1-8 0c0-3 2-4 2-4s-4 3-4 7a6 6 0 0 0 12 0c0-6-6-11-6-11z" />
              </svg>
            </div>
            <div className="z-lbl">{t("zine.tile.fallingBehind")}</div>
            <div className="z-val">
              {behindCount === 0 ? "✓" : totalBehindTopics}
              <span className="z-u">
                {behindCount === 0
                  ? t("zine.tile.caughtUp")
                  : (totalBehindTopics === 1 ? t("common.topic", "topic") : t("common.topics", "topics"))}
              </span>
            </div>
            <div className="z-hint">
              {behindCount === 0 ? t("zine.tile.allOnTrack") : t("zine.tile.coursesTrailing", { count: behindCount })}
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 02 — THIS WEEK */}
      <section className="z-sec">
        <div className="z-sec-h">
          <div className="z-num" data-c="cyan">02</div>
          <div className="z-title-wrap">
            <h2>{t("zine.thisWeekTitle")}</h2>
            <div className="z-sub">{t("zine.thisWeekSub", { count: eventsThisWeek })}</div>
          </div>
          {semesterLabel && <div className="z-meta">{semesterLabel.toUpperCase()}</div>}
        </div>
        <ZineWeek slots={data.slots} monday={monday} now={now} />
      </section>

      {/* SECTION 03 — THE COURSES */}
      <section className="z-sec">
        <div className="z-sec-h">
          <div className="z-num" data-c="pink">03</div>
          <div className="z-title-wrap">
            <h2>{t("zine.coursesTitle")}</h2>
            <div className="z-sub">{t("zine.coursesSub", { count: data.courses.length })}</div>
          </div>
          <div className="z-meta">{totalEcts} ECTS</div>
        </div>
        <div className="z-courses">
          {data.courses.map((c, i) => {
            const fb = data.fall_behind.find((f) => f.course_code === c.code);
            const nextL = fb?.next_lecture_at ? relLabel(parseISO(fb.next_lecture_at), now) : null;
            const pct = progressPerCourse[i] ?? 0;
            const ordinals = ["one", "two", "three", "four", "five", "six", "seven", "eight"];
            return (
              <Link
                key={c.code}
                to={`/courses/${c.code}`}
                className="z-ccard"
                style={{ "--accent": cv(c.code) } as React.CSSProperties}
              >
                <div className="z-bign">{ordinals[i] ?? String(i + 1)}</div>
                <div className="z-stickertag">{c.code}</div>
                <div className="z-nm">{c.full_name}</div>
                <div className="z-cmeta">
                  {c.module_code && <span>{c.module_code}</span>}
                  {c.module_code && c.ects != null && <span>·</span>}
                  {c.ects != null && <span>{c.ects} ECTS</span>}
                  {c.ects != null && c.language && <span>·</span>}
                  {c.language && <span>{c.language.slice(0, 2).toUpperCase()}</span>}
                </div>
                {nextL && (
                  <div className="z-nextl">
                    {t("zine.nextLecture")} <b>{nextL.label}</b>
                  </div>
                )}
                {fb && fb.topics.length > 0 && (
                  <span className="z-behindtag">{t("zine.behindTag", { n: fb.topics.length })}</span>
                )}
                <div className="z-progrow">
                  <div className="z-prog">
                    <div className="z-f" style={{ "--w": `${pct}%`, "--accent": cv(c.code) } as React.CSSProperties} />
                  </div>
                  <span className="z-pct">{pct}%</span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* SECTION 04 — THE QUEUE */}
      <section className="z-sec">
        <div className="z-sec-h">
          <div className="z-num" data-c="lime">04</div>
          <div className="z-title-wrap">
            <h2>{t("zine.queueTitle")}</h2>
            <div className="z-sub">{t("zine.queueSub")}</div>
          </div>
          <div className="z-meta">
            {t("zine.queueMeta", { dl: openDeliverables.length, open: tasksOpen.length })}
          </div>
        </div>
        <div className="z-twocol">
          <ZineDeadlines deliverables={openDeliverables} now={now} />
          <ZineTasks tasks={data.tasks} now={now} />
        </div>
      </section>
    </div>
  );
}

function ZineWeek({
  slots, monday, now,
}: {
  slots: { id: string; weekday: number; start_time: string; end_time: string; kind: string; room?: string; course_code: string }[];
  monday: Date;
  now: Date;
}) {
  const { i18n } = useTranslation();
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const wkLabel = i18n.language === "de" ? "KW" : "WK";
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
  const nowVisible =
    todayIdx >= 1 && todayIdx <= 5 &&
    now.getHours() >= sH && now.getHours() < sH + hours.length;

  const cw = isoWeek(monday);

  const days = [1, 2, 3, 4, 5].map((i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + (i - 1));
    return {
      i,
      name: d.toLocaleDateString(localeCode, { weekday: "short" }).toLowerCase(),
      d: `${pad(d.getDate())} ${d.toLocaleDateString(localeCode, { month: "short" }).toLowerCase()}`,
    };
  });

  return (
    <div className="z-week">
      <div className="z-week-inner">
        <div className="z-whead z-corner">
          <div className="z-dow">{wkLabel} {pad(cw)}</div>
          <div className="z-dn">{monday.toLocaleDateString(localeCode, { month: "short" }).toUpperCase()}</div>
        </div>
        {days.map((day) => (
          <div key={day.i} className={"z-whead" + (day.i === todayIdx ? " z-today" : "")}>
            <div className="z-dow">{day.name}</div>
            <div className="z-dn">{day.d}</div>
          </div>
        ))}
        <div className="z-wrail" style={{ height: hours.length * pxh }}>
          {hours.map((h) => (
            <div key={h} className="z-hr" style={{ height: pxh }}>
              <span>{pad(h)}:00</span>
            </div>
          ))}
        </div>
        {days.map((day) => (
          <div key={day.i}
               className={"z-wcol" + (day.i === todayIdx ? " z-today" : "")}
               style={{ height: hours.length * pxh }}>
            {day.i === todayIdx && nowVisible && <div className="z-nowline" style={{ top: nowTop }} />}
            {slots
              .filter((s) => s.weekday === day.i)
              .map((s) => (
                <div key={s.id}
                     className="z-wblk"
                     style={{
                       top: toTop(s.start_time.slice(0, 5)),
                       height: toH(s.start_time.slice(0, 5), s.end_time.slice(0, 5)) - 2,
                       "--accent": cv(s.course_code),
                     } as React.CSSProperties}>
                  <div className="z-tm">{s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}</div>
                  <div className="z-crow">
                    <span className="z-ccode">{s.course_code}</span>
                    <span className="z-kind">{s.kind}</span>
                  </div>
                  {s.room && <div className="z-rm">↳ {s.room}</div>}
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function ZineDeadlines({
  deliverables, now,
}: {
  deliverables: { id: string; course_code: string; kind: string; name: string; due_at: string; status: string }[];
  now: Date;
}) {
  const { t, i18n } = useTranslation();
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const navigate = useNavigate();
  return (
    <div className="z-pnl">
      <div className="z-phead">
        <span className="z-title">{t("zine.deadlinesTitle")}</span>
        <span className="z-note">{t("zine.deadlinesNote")}</span>
      </div>
      {deliverables.length === 0 && (
        <div style={{ padding: 20, color: "var(--z-ink-3)", fontSize: 12 }}>{t("zine.nothingOpen")}</div>
      )}
      {deliverables.slice(0, 10).map((d) => {
        const rt = relLabel(parseISO(d.due_at), now);
        const t = new Date(d.due_at);
        const abs = `${pad(t.getDate())} ${t.toLocaleDateString(localeCode, { month: "short" }).toUpperCase()} · ${pad(t.getHours())}:${pad(t.getMinutes())}`;
        return (
          <div key={d.id} className="z-drow" onClick={() => navigate(`/courses/${d.course_code}`)}>
            <span className="z-stickerc" style={{ "--accent": cv(d.course_code) } as React.CSSProperties}>
              {d.course_code}
            </span>
            <div className="z-core">
              <div className="z-nm">{d.name}</div>
              <div className="z-sub">{d.kind} · {abs}</div>
            </div>
            <span className="z-rt" data-sev={rt.sev}>{rt.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function ZineTasks({
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

  const visible = tasks.slice(0, 12);
  return (
    <div className="z-pnl" data-tone="tasks">
      <div className="z-phead">
        <span className="z-title">{t("zine.tasksTitle")}</span>
        <span className="z-note">{t("zine.tasksNote")}</span>
      </div>
      {visible.length === 0 && (
        <div style={{ padding: 20, color: "var(--z-ink-3)", fontSize: 12 }}>{t("zine.noTasks")}</div>
      )}
      {visible.map((t) => {
        const isDone = t.status === "done" || t.status === "skipped";
        const rt = t.due_at ? relLabel(parseISO(t.due_at), now) : null;
        return (
          <div key={t.id} className="z-trow" style={{ opacity: isDone ? 0.55 : 1 }}>
            <span className="z-chk" data-c={isDone} onClick={() => toggle(t.id, isDone)}>
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 12l5 5L20 6" />
              </svg>
            </span>
            <span className="z-stickerc" style={{ "--accent": t.course_code ? cv(t.course_code) : "var(--z-ink-3)" } as React.CSSProperties}>
              {t.course_code ?? "—"}
            </span>
            <div className="z-core">
              <div className="z-nm" style={{ textDecoration: isDone ? "line-through" : "none" }}>{t.title}</div>
            </div>
            {rt && <span className="z-rt" data-sev={rt.sev}>{rt.label}</span>}
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
