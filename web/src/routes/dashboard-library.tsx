/**
 * LIBRARY (archival) dashboard — ported from docs/examples/study-dashboard-v4.html.
 * Renders when theme === "library". Uses real API data. Omits invented flair:
 * "Ex Libris" call numbers, weather, price tag, "est. MMXXIV", the printer's
 * colophon. Keeps the archival aesthetic: sepia palette, drop caps, roman
 * numerals, double rules.
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

const ROMAN_LOWER = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"];
const ROMAN_UPPER = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];

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
  if (m < 0)  return { label: "—",           sev: "past"   as const };
  if (m < 60) return { label: `+${m} min`,   sev: "urgent" as const };
  if (h < 24) return { label: `+${h} hrs`,   sev: h < 6 ? ("urgent" as const) : ("soon" as const) };
  if (d <= 3) return { label: `+${d} days`,  sev: "soon"   as const };
  return         { label: `+${d} days`,  sev: "later"  as const };
}

function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || "A";
}

export function LibraryDashboard() {
  const { t, i18n } = useTranslation();
  const { data, isPending, error } = useDashboard();
  const settings = useAppSettings();

  if (isPending) {
    return <div className="l-page"><div style={{ padding: 48 }}>{t("library.loading")}</div></div>;
  }
  if (error || !data) {
    return <div className="l-page"><div style={{ padding: 48, color: "var(--l-red)" }}>{t("library.loadFailed")}</div></div>;
  }

  const now = parseISO(data.now);
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const displayName = (settings.data?.display_name ?? "").trim() || t("library.fallbackName");
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

  const nextDueDays = nextDue ? Math.max(0, differenceInCalendarDays(parseISO(nextDue.due_at), now)) : null;
  const tasksUrgent = tasksOpen.filter((task) => task.priority === "urgent").length;
  const tasksHigh = tasksOpen.filter((task) => task.priority === "high").length;
  const tasksThisWeek = tasksOpen.filter(
    (task) => task.due_at && differenceInCalendarDays(parseISO(task.due_at), now) <= 7
  ).length;

  const dateLong = now.toLocaleDateString(localeCode, {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  const dateShort = now.toLocaleDateString(localeCode, {
    weekday: "short", day: "2-digit", month: "short",
  });
  const morningOf = now.toLocaleDateString(localeCode, { day: "numeric", month: "long" });

  const cw = isoWeek(monday);
  const registerTitle = t("library.registerTitle", { name: firstName });

  return (
    <div className="l-page">
      {/* MASTHEAD */}
      <header className="l-masthead">
        <div className="l-eyebrow">
          <span>
            {semesterLabel && <>{t("library.term")} · <b>{semesterLabel}</b></>}
          </span>
          {institution && <span>{institution}</span>}
          <span>{t("library.number")} <b>{pad(cw)}</b></span>
        </div>
        <h1 className="l-title0">{registerTitle}</h1>
        <div className="l-dek">{t("library.registerSub")}</div>
        <div className="l-rule-strip">
          <span>{dateLong}</span>
          {semesterLabel && <span><b>{semesterLabel}</b> · {t("library.week")} <b>{pad(cw)}</b></span>}
          <span>{pad(now.getHours())}:{pad(now.getMinutes())}</span>
        </div>
      </header>

      {/* SALUTATION */}
      <section className="l-salut">
        <div className="l-drop">{initial(displayName)}</div>
        <div className="l-body">
          <div className="l-from">{t("library.editorDesk")}</div>
          <div className="l-greeting">
            {t("library.greetingTo")} <span className="l-nm">{displayName}</span>, {t("library.greetingOnMorning", { date: morningOf })}<br />
            {t("library.greetingBrief")}
          </div>
          {behindCount > 0 ? (
            <div className="l-note">
              {t("library.noteInArrears", { topics: totalBehindTopics, count: behindCount })}
            </div>
          ) : (
            <div className="l-note">
              {t("library.noteClear")}
            </div>
          )}
          {nextEvent && firstSlot && (
            <div className="l-next">
              {t("library.nextEngagement")}<span>—</span>
              <b>{nextEvent.code}</b>
              <span>{t("library.inRel", { rel: firstSlot.label.replace("+", "") })}</span>
            </div>
          )}
        </div>
        <div className="l-stamp">
          <div className="l-date">{dateShort}</div>
          <div>{pad(now.getHours())}:{pad(now.getMinutes())}</div>
        </div>
      </section>

      {/* NOTICE */}
      {behindCount > 0 && (
        <>
          <div className="l-sec-head">
            <div className="l-roman">§ I</div>
            <div className="l-t">{t("library.notice")} <em>{t("library.noticeSub")}</em></div>
            <div className="l-meta">{t("library.noticeAsOf", { time: `${pad(now.getHours())}:${pad(now.getMinutes())}` })}</div>
          </div>
          <div className="l-notice">
            <span className="l-tag">{t("library.noticeTag")}</span>
            <div>
              <h3>
                {t("library.noticeHeadlinePre", { count: totalBehindTopics, topics: totalBehindTopics })} <em>{t("library.overdue")}</em>{t("library.noticeHeadlineMid", { count: behindCount })}
              </h3>
              <ul>
                {behindCourses.slice(0, 4).map((b, i) => {
                  const nextStr = b.next_lecture_at
                    ? relLabel(parseISO(b.next_lecture_at), now).label
                    : "—";
                  return (
                    <li key={b.course_code}>
                      <span className="l-rn">{ROMAN_UPPER[i]}.</span>
                      <span>
                        <b>{b.course_code}</b> — {t("library.topicsAbbr", { count: b.topics.length })}; {t("library.nextLectureLabel")}{" "}
                        <b>{nextStr}</b>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div className="l-dots">
              {data.courses.map((c) => {
                const fb = data.fall_behind.find((f) => f.course_code === c.code);
                const ok = !fb || fb.severity === "ok" || fb.topics.length === 0;
                const color = ok
                  ? "var(--l-green)"
                  : fb!.severity === "critical"
                  ? "var(--l-red)"
                  : "var(--l-mustard)";
                return (
                  <div key={c.code} className="l-row" style={{ "--accent": color } as React.CSSProperties}>
                    <span className="l-dot" data-state={ok ? "ok" : "hot"} />
                    <span className="l-code">{c.code}</span>
                    <span>{progressPerCourse[data.courses.indexOf(c)] ?? 0}%</span>
                    <span className="l-sev" data-state={ok ? "ok" : "hot"}>
                      {ok ? t("library.steady") : t("library.behind")}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* LEDGER */}
      <div className="l-sec-head">
        <div className="l-roman">§ {behindCount > 0 ? "II" : "I"}</div>
        <div className="l-t">{t("library.ledger")} <em>{t("library.ledgerSub")}</em></div>
        <div className="l-meta">{t("library.ledgerMeta")}</div>
      </div>
      <div className="l-ledger">
        <div className="l-ltile" data-tone={nextDueDays !== null && nextDueDays <= 1 ? "critical" : nextDueDays !== null && nextDueDays <= 3 ? "warn" : "default"}>
          <div className="l-topline"><span className="l-rn">i.</span><span className="l-lbl">{t("library.tile.nextDeadline")}</span></div>
          <div className="l-val">
            {nextDue ? <>{nextDueDays ?? 0}<span className="l-u">{nextDueDays === 1 ? t("library.tile.day") : t("library.tile.days")}</span></> : "—"}
          </div>
          <div className="l-hint">
            {nextDue ? `${nextDue.course_code} — ${nextDue.name}` : t("library.tile.nothingOpen")}
          </div>
        </div>
        <div className="l-ltile" data-tone={tasksUrgent > 0 ? "critical" : tasksThisWeek > 3 ? "warn" : "default"}>
          <div className="l-topline"><span className="l-rn">ii.</span><span className="l-lbl">{t("library.tile.tasksOpen")}</span></div>
          <div className="l-val">{tasksOpen.length}<span className="l-u">{t("library.tile.tasksOfTotal", { total: data.tasks.length })}</span></div>
          <div className="l-hint">{t("library.tile.urgentHigh", { urgent: tasksUrgent, high: tasksHigh })}</div>
        </div>
        <div className="l-ltile" data-tone={avgProgress >= 70 ? "ok" : avgProgress < 25 ? "warn" : "default"}>
          <div className="l-topline"><span className="l-rn">iii.</span><span className="l-lbl">{t("library.tile.meanProgress")}</span></div>
          <div className="l-val">{avgProgress}<span className="l-u">{t("library.tile.perCent")}</span></div>
          <div className="l-hint">
            {data.courses.map((c, i) => `${c.code} ${pad(progressPerCourse[i] ?? 0)}`).join(" · ")}
          </div>
        </div>
        <div className="l-ltile" data-tone={behindCount === 0 ? "ok" : behindCourses.some((b) => b.severity === "critical") ? "critical" : "warn"}>
          <div className="l-topline"><span className="l-rn">iv.</span><span className="l-lbl">{t("library.tile.inArrears")}</span></div>
          <div className="l-val">
            {behindCount === 0 ? t("library.tile.nil") : totalBehindTopics}
            <span className="l-u">
              {behindCount === 0 ? "" : t("library.tile.topic", { count: totalBehindTopics })}
            </span>
          </div>
          <div className="l-hint">
            {behindCount === 0
              ? t("library.tile.volumeOnSchedule")
              : t("library.tile.acrossVolumes", { count: behindCount })}
          </div>
        </div>
      </div>

      {/* TABLEAU */}
      <div className="l-sec-head">
        <div className="l-roman">§ {behindCount > 0 ? "III" : "II"}</div>
        <div className="l-t">{t("library.tableau")} <em>{t("library.tableauSub")}</em></div>
        <div className="l-meta">{t("library.engagementsWk", { count: eventsThisWeek, wk: ROMAN_LOWER[cw - 1] ?? pad(cw) })}</div>
      </div>
      <LibraryTableau slots={data.slots} monday={monday} now={now} localeCode={localeCode} />

      {/* PLATES */}
      <div className="l-sec-head">
        <div className="l-roman">§ {behindCount > 0 ? "IV" : "III"}</div>
        <div className="l-t">{t("library.volumes")} <em>{t("library.volumesSub")}</em></div>
        <div className="l-meta">{t("library.ectsModules", { ects: totalEcts, count: data.courses.length })}</div>
      </div>
      <div className="l-plates">
        {data.courses.map((c, i) => {
          const fb = data.fall_behind.find((f) => f.course_code === c.code);
          const nextL = fb?.next_lecture_at ? relLabel(parseISO(fb.next_lecture_at), now) : null;
          const pct = progressPerCourse[i] ?? 0;
          const behind = fb?.topics.length ?? 0;
          return (
            <Link
              key={c.code}
              to={`/courses/${c.code}`}
              className="l-platecard"
              data-plate={ROMAN_UPPER[i] ?? String(i + 1)}
              style={{ "--accent": cv(c.code) } as React.CSSProperties}
            >
              <div className="l-codeband">
                <span className="l-seal">{c.code}</span>
                <span className="l-roman">{t("library.volNumber", { n: ROMAN_UPPER[i] ?? String(i + 1) })}</span>
                <span className="l-flag" data-ok={behind === 0}>
                  {behind === 0 ? t("library.ok") : `−${behind}`}
                </span>
              </div>
              <div className="l-tit">{c.full_name}</div>
              <div className="l-meta">
                {[c.module_code, c.ects != null ? `${c.ects} ECTS` : null, c.language?.slice(0, 2).toUpperCase()]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              {nextL && (
                <div className="l-next">
                  {t("library.nextLectureLabel")} <b>{nextL.label}</b>
                </div>
              )}
              <div className="l-prog">
                <div className="l-bar">
                  <div className="l-f" style={{ "--w": `${pct}%` } as React.CSSProperties} />
                </div>
                <div className="l-pct">{pad(pct)}%</div>
              </div>
            </Link>
          );
        })}
      </div>

      {/* REGISTERS */}
      <div className="l-sec-head">
        <div className="l-roman">§ {behindCount > 0 ? "V" : "IV"}</div>
        <div className="l-t">{t("library.registers")} <em>{t("library.registersSub")}</em></div>
        <div className="l-meta">{t("library.registersMeta", { dl: openDeliverables.length, open: tasksOpen.length })}</div>
      </div>
      <div className="l-twocol">
        <LibraryDeadlines deliverables={openDeliverables} now={now} localeCode={localeCode} />
        <LibraryTasks tasks={data.tasks} now={now} />
      </div>
    </div>
  );
}

function LibraryTableau({
  slots, monday, now, localeCode,
}: {
  slots: { id: string; weekday: number; start_time: string; end_time: string; kind: string; room?: string; course_code: string }[];
  monday: Date;
  now: Date;
  localeCode: string;
}) {
  const { t } = useTranslation();
  const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
  const pxh = 46;
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

  const days = [1, 2, 3, 4, 5].map((i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + (i - 1));
    return {
      i,
      name: d.toLocaleDateString(localeCode, { weekday: "short" }) + ".",
      d: `${pad(d.getDate())} ${d.toLocaleDateString(localeCode, { month: "short" })}`,
    };
  });

  const cw = isoWeek(monday);

  return (
    <div className="l-tableau">
      <div className="l-tgrid">
        <div className="l-th l-corner">
          <div className="l-dow">{t("library.wk")} · {ROMAN_UPPER[cw - 1] ?? pad(cw)}</div>
          <div className="l-dn">{monday.toLocaleDateString(localeCode, { month: "short" }).toUpperCase()}</div>
        </div>
        {days.map((day) => (
          <div key={day.i} className={"l-th" + (day.i === todayIdx ? " l-today" : "")}>
            <div className="l-dow">{day.name}</div>
            <div className="l-dn">{day.d}</div>
          </div>
        ))}
        <div className="l-rail" style={{ height: hours.length * pxh }}>
          {hours.map((h) => (
            <div key={h} className="l-hr" style={{ height: pxh }}>
              <span>{pad(h)}:00</span>
            </div>
          ))}
        </div>
        {days.map((day) => (
          <div key={day.i}
               className={"l-tcol" + (day.i === todayIdx ? " l-today" : "")}
               style={{ height: hours.length * pxh }}>
            {day.i === todayIdx && nowVisible && (
              <div className="l-nowrule" data-t={nowStr} style={{ top: nowTop }} />
            )}
            {slots
              .filter((s) => s.weekday === day.i)
              .map((s) => (
                <div key={s.id}
                     className="l-event"
                     style={{
                       top: toTop(s.start_time.slice(0, 5)),
                       height: toH(s.start_time.slice(0, 5), s.end_time.slice(0, 5)) - 2,
                       "--accent": cv(s.course_code),
                     } as React.CSSProperties}>
                  <div className="l-tm">{s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}</div>
                  <div className="l-ttl">
                    <span className="l-cc">{s.course_code}</span> · {s.kind}
                  </div>
                  {s.room && <div className="l-rm">— {s.room}</div>}
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function LibraryDeadlines({
  deliverables, now, localeCode,
}: {
  deliverables: { id: string; course_code: string; kind: string; name: string; due_at: string; status: string }[];
  now: Date;
  localeCode: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="l-register">
      <div className="l-rhead">
        <span className="l-ti">{t("library.panel.deadlines")}</span>
        <span className="l-dek">{t("library.panel.deadlinesSub")}</span>
        <span className="l-n">N = {String(deliverables.length).padStart(2, "0")}</span>
      </div>
      {deliverables.length === 0 && (
        <div style={{ padding: 18, fontStyle: "italic", color: "var(--l-ink-3)" }}>
          {t("library.panel.nothingOpen")}
        </div>
      )}
      {deliverables.slice(0, 10).map((d, i) => {
        const rt = relLabel(parseISO(d.due_at), now);
        const dt = new Date(d.due_at);
        const abs = `${pad(dt.getDate())} ${dt.toLocaleDateString(localeCode, { month: "short" })} · ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
        return (
          <div key={d.id} className="l-ledrow" onClick={() => navigate(`/courses/${d.course_code}`)}>
            <span className="l-rnn">{ROMAN_LOWER[i] ?? String(i + 1)}.</span>
            <span className="l-sealc" style={{ "--accent": cv(d.course_code) } as React.CSSProperties}>
              {d.course_code}
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="l-nm">{d.name}</div>
              <div className="l-sub">{d.kind} · {abs}</div>
            </div>
            <span className="l-stat" data-s={d.status}>{t(`kinds.status.${d.status}`, d.status.replace("_", " "))}</span>
            <span className="l-rt" data-sev={rt.sev}>{rt.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function LibraryTasks({
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
    <div className="l-register">
      <div className="l-rhead">
        <span className="l-ti">{t("library.panel.tasks")}</span>
        <span className="l-dek">{t("library.panel.tasksSub")}</span>
        <span className="l-n">N = {String(openCount).padStart(2, "0")}</span>
      </div>
      {visible.length === 0 && (
        <div style={{ padding: 18, fontStyle: "italic", color: "var(--l-ink-3)" }}>
          {t("library.panel.noTasks")}
        </div>
      )}
      {visible.map((task, i) => {
        const isDone = task.status === "done" || task.status === "skipped";
        const rt = task.due_at ? relLabel(parseISO(task.due_at), now) : null;
        return (
          <div key={task.id} className="l-trow" style={{ opacity: isDone ? 0.55 : 1 }}>
            <span className="l-rnn" style={{ fontFamily: "var(--l-font-mono)", fontSize: 10, color: "var(--l-sepia)", letterSpacing: "0.1em", textAlign: "right" }}>
              {ROMAN_LOWER[i] ?? String(i + 1)}.
            </span>
            <span className="l-chk" data-c={isDone} onClick={() => toggle(task.id, isDone)} />
            <span
              className="l-sealc"
              style={{ "--accent": task.course_code ? cv(task.course_code) : "var(--l-ink-3)" } as React.CSSProperties}
            >
              {task.course_code ?? "—"}
            </span>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontFamily: "var(--l-font-serif)",
                  fontSize: 14,
                  fontWeight: 600,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  textDecoration: isDone ? "line-through" : "none",
                  color: "var(--l-ink)",
                }}
              >
                {task.title}
              </div>
            </div>
            {rt && (
              <span
                className="l-rt"
                data-sev={rt.sev}
                style={{
                  fontFamily: "var(--l-font-mono)",
                  fontSize: 10.5,
                  fontWeight: 600,
                  textAlign: "right",
                  letterSpacing: "0.06em",
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

function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}
