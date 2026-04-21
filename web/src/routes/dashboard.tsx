import {
  Clock,
  ListChecks,
  TrendingUp,
  Flame,
  Loader2,
  Sparkles,
} from "lucide-react";
import { differenceInCalendarDays, parseISO } from "date-fns";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Greeting } from "@/components/dashboard/greeting";
import { FallBehindBanner } from "@/components/dashboard/fall-behind-banner";
import { MetricTile } from "@/components/dashboard/metric-tile";
import { WeeklyGrid } from "@/components/dashboard/weekly-grid";
import { DeadlinesList } from "@/components/dashboard/deadlines-list";
import { CourseCard } from "@/components/dashboard/course-card";
import { TaskInbox } from "@/components/dashboard/task-inbox";
import { useAppSettings, useDashboard } from "@/lib/queries";
import { fmtBerlin, relative } from "@/lib/time";
import { useTranslation } from "react-i18next";
import type { CourseCode } from "@/data/types";
import { normalizeTheme } from "@/lib/themes";
import { TerminalDashboard } from "./dashboard-terminal";
import { ZineDashboard } from "./dashboard-zine";
import { LibraryDashboard } from "./dashboard-library";
import { SwissDashboard } from "./dashboard-swiss";

type DashboardSummaryTopic = { course_code: string; status: string };

export default function Dashboard() {
  const settings = useAppSettings();
  const theme = normalizeTheme(settings.data?.theme);
  if (theme === "terminal") return <TerminalDashboard />;
  if (theme === "zine") return <ZineDashboard />;
  if (theme === "library") return <LibraryDashboard />;
  if (theme === "swiss") return <SwissDashboard />;
  return <EditorialDashboard />;
}

function EditorialDashboard() {
  const { t } = useTranslation();
  const { data, isPending, error } = useDashboard();

  if (isPending) {
    return (
      <div className="px-6 md:px-0 py-12 flex items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="px-6 md:px-0 py-12 text-center">
        <p className="text-sm text-critical">{t("dashboard.loadFailed")}</p>
        <p className="text-xs text-muted mt-1">{(error as Error | null)?.message}</p>
      </div>
    );
  }

  const now = parseISO(data.now);

  if (data.courses.length === 0) {
    return (
      <>
        <DashboardTopStrip now={now} />
        <div className="px-4 md:px-0 max-w-[1200px] mx-auto w-full">
          <Greeting now={now} subline="Let's set things up." />
          <EmptyDashboard />
        </div>
      </>
    );
  }

  const openDeliverables = [...data.deliverables]
    .filter((d) => d.status === "open" || d.status === "in_progress")
    .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime());
  const nextDue = openDeliverables[0];

  const tasksOpen = data.tasks.filter((t) => t.status !== "done" && t.status !== "skipped");
  const tasksThisWeek = tasksOpen.filter(
    (t) => t.due_at && differenceInCalendarDays(parseISO(t.due_at), now) <= 7
  ).length;
  const tasksUrgent = tasksOpen.filter((t) => t.priority === "urgent").length;
  const tasksHigh = tasksOpen.filter((t) => t.priority === "high").length;

  const progressPerCourse = data.courses.map((c) => progressFor(c.code, data.study_topics));
  const avgProgress = progressPerCourse.length
    ? Math.round(progressPerCourse.reduce((s, v) => s + v, 0) / progressPerCourse.length)
    : 0;

  const totalEcts = data.courses.reduce((s, c) => s + (c.ects ?? 0), 0);

  const behindCourses = data.fall_behind.filter((f) => f.severity !== "ok");
  const behindCount = behindCourses.length;
  const totalBehindTopics = behindCourses.reduce((s, c) => s + c.topics.length, 0);
  const hasCritical = behindCourses.some((c) => c.severity === "critical");

  const nextEvent = data.fall_behind
    .map((f) =>
      f.next_lecture_at
        ? { code: f.course_code as CourseCode, at: parseISO(f.next_lecture_at) }
        : null
    )
    .filter((x): x is { code: CourseCode; at: Date } => x !== null)
    .sort((a, b) => a.at.getTime() - b.at.getTime())[0];

  // Mon of current week in Berlin
  const monday = startOfBerlinWeek(now);
  const friday = new Date(monday);
  friday.setDate(monday.getDate() + 4);
  const todayWeekday = ((now.getDay() + 6) % 7) + 1;

  const eventsThisWeek = data.slots.filter((s) => s.weekday >= 1 && s.weekday <= 5).length;

  const nextUpBehind = nextEvent
    ? behindCourses.find((b) => b.course_code === nextEvent.code)
    : undefined;
  const nextUpUnstudied = nextUpBehind?.topics.length ?? 0;
  const subline =
    nextUpUnstudied > 0
      ? t(
          nextUpUnstudied === 1 ? "dashboard.falling_behind_one" : "dashboard.falling_behind_other",
          { count: nextUpUnstudied, code: nextEvent!.code }
        )
      : behindCount === 0
      ? t("dashboard.all_caught_up")
      : undefined;

  // Next-deadline tone
  const nextDueDays = nextDue
    ? Math.max(0, differenceInCalendarDays(parseISO(nextDue.due_at), now))
    : null;
  const nextDueTone =
    nextDue && nextDue.due_at
      ? (() => {
          const sev = relative(nextDue.due_at, now).severity;
          return sev === "urgent" ? "critical" : sev === "soon" ? "warn" : "default";
        })()
      : "default";
  const nextDueLabel = nextDue ? relative(nextDue.due_at, now).label.replace("in ", "") : "—";
  const nextDueHint = nextDue
    ? `${nextDue.course_code} · ${nextDue.name}`
    : t("dashboard.tile.noOpenDeliverables");

  const taskUnit =
    tasksOpen.length === 0
      ? ""
      : `open${tasksOpen.length - tasksThisWeek > 0 ? "" : " · due by Sun"}`;

  const behindBreakdown = data.courses
    .map((c) => {
      const fb = data.fall_behind.find((f) => f.course_code === c.code);
      return `${c.code} ${fb?.topics.length ?? 0}`;
    })
    .join(" · ");

  return (
    <>
      <DashboardTopStrip now={now} />
      <div className="px-4 md:px-0 max-w-[1200px] mx-auto w-full">
        <Greeting now={now} nextUp={nextEvent ?? null} subline={subline} />

      <FallBehindBanner
        items={data.fall_behind.map((f) => ({
          course_code: f.course_code as CourseCode,
          topics: f.topics,
          last_covered_on: f.last_covered_on ? new Date(f.last_covered_on) : null,
          next_lecture_at: f.next_lecture_at ? new Date(f.next_lecture_at) : null,
          severity: f.severity,
        }))}
      />

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mb-5">
        <MetricTile
          label={t("dashboard.tile.nextDeadline")}
          value={nextDueDays === null ? "—" : nextDueLabel}
          hint={nextDueHint}
          icon={<Clock className="h-3.5 w-3.5" />}
          tone={nextDueTone as "default" | "warn" | "critical"}
        />
        <MetricTile
          label={t("dashboard.tile.tasksThisWeek")}
          value={tasksThisWeek}
          unit={taskUnit || undefined}
          hint={
            tasksOpen.length === 0
              ? t("dashboard.tile.allClear")
              : `${t("dashboard.tile.urgent", { n: tasksUrgent })} · ${t("dashboard.tile.high", { n: tasksHigh })}`
          }
          icon={<ListChecks className="h-3.5 w-3.5" />}
          tone={tasksUrgent > 0 ? "critical" : tasksThisWeek > 3 ? "warn" : "default"}
        />
        <MetricTile
          label={t("dashboard.tile.avgProgress")}
          value={avgProgress}
          unit="%"
          hint={
            t(
              data.courses.length === 1 ? "dashboard.tile.acrossCourses" : "dashboard.tile.acrossCoursesPlural",
              { count: data.courses.length }
            ) + ` · Σ ${totalEcts} ECTS`
          }
          icon={<TrendingUp className="h-3.5 w-3.5" />}
          tone={avgProgress < 25 ? "warn" : avgProgress >= 70 ? "ok" : "default"}
        />
        <MetricTile
          label={t("dashboard.tile.behind")}
          value={behindCount === 0 ? "✓" : behindCount}
          unit={
            behindCount === 0
              ? t("dashboard.tile.onTrack")
              : `${totalBehindTopics}`
          }
          hint={behindCount === 0 ? t("dashboard.tile.allCaughtUp") : behindBreakdown}
          icon={<Flame className="h-3.5 w-3.5" />}
          tone={behindCount === 0 ? "ok" : hasCritical ? "critical" : "warn"}
        />
      </section>

      <SectionHeader
        title={t("dashboard.section.thisWeek")}
        meta={`${fmtBerlin(monday, "EEE d MMM")} – ${fmtBerlin(friday, "EEE d MMM")} · ${t(
          eventsThisWeek === 1 ? "dashboard.section.eventsMeta" : "dashboard.section.eventsMetaPlural",
          { count: eventsThisWeek }
        )}`}
      />
      <WeeklyGrid
        slots={data.slots}
        todayWeekday={todayWeekday}
        monday={monday}
        now={now}
      />

      <SectionHeader title={t("dashboard.section.courses")} meta={`${data.courses.length}`} />
      <section
        className="grid gap-2.5"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" } as CSSProperties}
      >
        {data.courses.map((c, i) => {
          const fb = data.fall_behind.find((f) => f.course_code === c.code);
          return (
            <CourseCard
              key={c.code}
              course={c}
              progress={progressPerCourse[i]}
              nextLectureAt={fb?.next_lecture_at ? new Date(fb.next_lecture_at) : null}
              fallBehind={{
                course_code: c.code,
                topics: fb?.topics ?? [],
                last_covered_on: fb?.last_covered_on ? new Date(fb.last_covered_on) : null,
                next_lecture_at: fb?.next_lecture_at ? new Date(fb.next_lecture_at) : null,
                severity: fb?.severity ?? "ok",
              }}
            />
          );
        })}
      </section>

      <SectionHeader title={t("dashboard.section.whatsNext")} meta={`${t("nav.deadlines")} · ${t("nav.tasks")}`} />
      <div className="grid gap-3 lg:[grid-template-columns:1.15fr_1fr] items-start">
        <div className="card overflow-hidden">
          <PanelHeader
            title={t("dashboard.section.upcomingDeadlines")}
            meta={`${openDeliverables.length} · ${t("dashboard.section.next3Weeks")}`}
          />
          <DeadlinesList deliverables={data.deliverables} />
        </div>
        <div className="card overflow-hidden">
          <PanelHeader
            title={t("dashboard.section.taskInbox")}
            meta={t("dashboard.section.openCount", { count: tasksOpen.length })}
          />
          <TaskInbox tasks={data.tasks} courses={data.courses} />
        </div>
      </div>
      </div>
    </>
  );
}

function DashboardTopStrip({ now }: { now: Date }) {
  const { i18n } = useTranslation();
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const settings = useAppSettings();
  const semesterLabel = settings.data?.semester_label?.trim() || null;
  const semesterWeek = computeSemesterWeek(now, settings.data?.semester_start);
  const wd = now.toLocaleDateString(localeCode, { weekday: "short" });
  const dm = `${now.getDate()} ${now.toLocaleDateString(localeCode, { month: "short" })}`;

  const items: { key: string; node: React.ReactNode }[] = [
    { key: "wd", node: <span className="text-fg font-medium">{wd}</span> },
    { key: "dm", node: <span>{dm}</span> },
  ];
  if (semesterLabel) {
    items.push({ key: "sem", node: <span>{semesterLabel}</span> });
  }
  if (semesterWeek !== null) {
    items.push({
      key: "week",
      node: <span>Week {String(semesterWeek).padStart(2, "0")}</span>,
    });
  }

  return (
    <div className="md:hidden border-b border-hairline bg-bg/85 backdrop-blur-sm sticky top-0 z-20">
      <div
        className="px-4 flex items-center justify-center gap-2 font-mono text-[11px] text-muted tracking-[0.04em]"
        style={{
          paddingTop: "calc(env(safe-area-inset-top) + 0.5rem)",
          paddingBottom: "0.5rem",
        }}
      >
        {items.map((it, i) => (
          <span key={it.key} className="flex items-center gap-2 min-w-0">
            {i > 0 && <span className="text-subtle">·</span>}
            <span className="truncate">{it.node}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function computeSemesterWeek(now: Date, startIso: string | null | undefined): number | null {
  if (!startIso) return null;
  const start = new Date(startIso + "T00:00:00");
  if (Number.isNaN(start.getTime())) return null;
  const ms = now.getTime() - start.getTime();
  if (ms < 0) return null; // pre-start: don't clutter the strip
  return Math.floor(ms / (7 * 24 * 60 * 60 * 1000)) + 1;
}

function SectionHeader({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-4 mt-8 mb-3">
      <h2
        className="font-serif text-[22px] font-normal tracking-[-0.005em] text-fg m-0 whitespace-nowrap"
        style={{ fontVariationSettings: '"opsz" 72, "SOFT" 30' }}
      >
        {title}
      </h2>
      {meta && <span className="font-mono text-[11.5px] text-muted tracking-[0.04em]">{meta}</span>}
    </div>
  );
}

function PanelHeader({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="px-4 pt-3.5 pb-2.5 flex items-baseline justify-between border-b border-hairline">
      <h3
        className="font-serif text-[17px] font-normal m-0 text-fg whitespace-nowrap"
        style={{ fontVariationSettings: '"opsz" 72, "SOFT" 30' }}
      >
        {title}
      </h3>
      {meta && <span className="font-mono text-[11px] text-muted tracking-[0.04em]">{meta}</span>}
    </div>
  );
}

function EmptyDashboard() {
  return (
    <div className="card p-6 md:p-10 flex flex-col items-center gap-5 text-center mt-4">
      <div className="w-12 h-12 rounded-full bg-surface-2 grid place-items-center">
        <Sparkles className="h-5 w-5 text-muted" />
      </div>
      <div>
        <h2
          className="font-serif text-[22px] md:text-[26px] font-normal tracking-[-0.005em]"
          style={{ fontVariationSettings: '"opsz" 72, "SOFT" 30' }}
        >
          Your dashboard is empty.
        </h2>
        <p className="text-sm text-muted mt-2 max-w-md mx-auto">
          Start by adding your courses — the rest of the app (schedule, lectures, topics,
          deadlines, tasks) hangs off them. You can also set your name and semester dates in
          Settings so the greeting feels personal.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 justify-center">
        <Link
          to="/courses"
          className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors bg-primary text-primary-fg hover:bg-primary/90 h-10 px-4 text-sm touch-target"
        >
          Add your first course
        </Link>
        <Link
          to="/settings"
          className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors bg-transparent text-fg hover:bg-surface-2 h-10 px-4 text-sm touch-target"
        >
          Set up profile
        </Link>
      </div>
    </div>
  );
}

function progressFor(code: string, topics: DashboardSummaryTopic[]): number {
  const weights: Record<string, number> = {
    not_started: 0,
    struggling: 0.2,
    in_progress: 0.5,
    studied: 0.9,
    mastered: 1,
  };
  const list = topics.filter((t) => t.course_code === code);
  if (list.length === 0) return 0;
  const total = list.reduce((s, t) => s + (weights[t.status] ?? 0), 0);
  return Math.round((total / list.length) * 100);
}

function startOfBerlinWeek(d: Date): Date {
  // ISO Monday of the given date's week, local time.
  const out = new Date(d);
  const day = out.getDay() || 7;
  if (day !== 1) out.setDate(out.getDate() - (day - 1));
  out.setHours(0, 0, 0, 0);
  return out;
}
