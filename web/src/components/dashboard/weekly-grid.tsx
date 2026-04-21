import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { Slot, CourseCode } from "@/data/types";
import { courseAccentVar } from "@/lib/theme";
import { cn } from "@/lib/cn";

const DAY_ISOS: (1 | 2 | 3 | 4 | 5)[] = [1, 2, 3, 4, 5];

const START_HOUR = 8;
const END_HOUR = 18;
const PX_PER_HOUR = 48;

function toTopPx(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return ((h + m / 60) - START_HOUR) * PX_PER_HOUR;
}
function slotHeight(start: string, end: string): number {
  return toTopPx(end) - toTopPx(start);
}
function hhmm(t: string): string {
  return t.length >= 5 ? t.slice(0, 5) : t;
}

export function WeeklyGrid({
  slots,
  todayWeekday,
  monday,
  now,
}: {
  slots: Slot[];
  todayWeekday: number;
  /** Monday of the current week (for date labels). */
  monday: Date;
  now: Date;
}) {
  const { i18n } = useTranslation();
  const localeCode = i18n.language === "de" ? "de-DE" : "en-GB";
  const hours = Array.from({ length: END_HOUR - START_HOUR + 1 }, (_, i) => START_HOUR + i);
  const totalHeight = (END_HOUR - START_HOUR) * PX_PER_HOUR;

  const nowMinutes = Number.isFinite(now.getTime())
    ? now.getHours() * 60 + now.getMinutes()
    : -1;
  const showNowLine =
    nowMinutes >= START_HOUR * 60 && nowMinutes < END_HOUR * 60;
  const nowTop = showNowLine
    ? ((nowMinutes - START_HOUR * 60) / 60) * PX_PER_HOUR
    : 0;
  const nowTimeStr = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

  const cw = isoWeek(monday);

  return (
    <div className="card overflow-hidden">
      {/* Same grid on all viewports — scrolls horizontally on narrow screens. */}
      <div className="overflow-x-auto">
      <div
        className="grid relative"
        style={{ gridTemplateColumns: `44px repeat(5, minmax(130px, 1fr))`, minWidth: 700 }}
      >
        {/* Corner */}
        <div className="flex flex-col gap-1 px-3 pt-3.5 pb-3 border-b border-border border-r border-hairline bg-surface-2">
          <span className="font-mono text-[10.5px] text-subtle tracking-[0.08em]">
            {i18n.language === "de" ? "KW" : "CW"} {cw}
          </span>
          <span className="font-mono text-[10.5px] text-muted">
            {monday.toLocaleString(localeCode, { month: "short" })}
          </span>
        </div>

        {DAY_ISOS.map((iso, i) => {
          const isToday = iso === todayWeekday;
          const date = new Date(monday);
          date.setDate(monday.getDate() + i);
          return (
            <div
              key={iso}
              className={cn(
                "relative flex flex-col gap-1 px-3 pt-3.5 pb-3 border-b border-border",
                i < DAY_ISOS.length - 1 && "border-r border-hairline"
              )}
            >
              <span
                className={cn(
                  "font-serif text-[16px] font-normal",
                  isToday ? "text-fg" : "text-fg-dim"
                )}
                style={{ fontVariationSettings: '"opsz" 72, "SOFT" 30' }}
              >
                {date.toLocaleDateString(localeCode, { weekday: "short" })}
              </span>
              <span className="font-mono text-[11px] text-muted tracking-[0.04em]">
                {date.getDate().toString().padStart(2, "0")}{" "}
                {date.toLocaleString(localeCode, { month: "short" })}
              </span>
              {isToday && (
                <>
                  <span aria-hidden className="absolute top-[17px] right-[10px]">
                    <span className="ink-dot" />
                  </span>
                  <span
                    aria-hidden
                    className="absolute bottom-[-1px] left-3 right-3 h-[2px] rounded-sm bg-fg"
                  />
                </>
              )}
            </div>
          );
        })}

        {/* Time rail */}
        <div
          className="bg-surface-2 pt-2 border-r border-hairline"
          style={{ height: totalHeight + 8 }}
        >
          {hours.slice(0, -1).map((h) => (
            <div
              key={h}
              className="relative font-mono text-[10.5px] text-subtle tracking-[0.04em] text-right pr-1.5"
              style={{ height: PX_PER_HOUR }}
            >
              <span className="absolute -top-1.5 right-1.5">
                {String(h).padStart(2, "0")}
              </span>
            </div>
          ))}
        </div>

        {/* Day columns */}
        {DAY_ISOS.map((iso, i) => {
          const isToday = iso === todayWeekday;
          const daySlots = slots.filter((s) => s.weekday === iso);
          return (
            <div
              key={iso}
              className={cn(
                "relative pb-4 pt-2 px-2",
                i < DAY_ISOS.length - 1 && "border-r border-hairline",
                isToday && "bg-[color-mix(in_oklch,var(--fg)_2.5%,var(--surface))]"
              )}
              style={{ minHeight: totalHeight + 8 }}
            >
              {isToday && showNowLine && (
                <div
                  aria-hidden
                  className="absolute left-0 right-0 z-10 pointer-events-none"
                  style={{ top: nowTop + 8 }}
                >
                  <div className="relative h-px bg-fg">
                    <span className="absolute -left-[3px] -top-[3px] w-[7px] h-[7px] rounded-full bg-fg" />
                    <span className="absolute right-1 -top-[8px] font-mono text-[9.5px] bg-fg text-bg px-1.5 py-[1px] rounded-sm tracking-[0.04em]">
                      {nowTimeStr}
                    </span>
                  </div>
                </div>
              )}
              {daySlots.map((slot) => (
                <LectureBlock key={slot.id} slot={slot} />
              ))}
            </div>
          );
        })}
      </div>
      </div>
    </div>
  );
}

function LectureBlock({ slot }: { slot: Slot }) {
  const top = toTopPx(hhmm(slot.start_time)) + 8; // +8 top padding of col
  const height = Math.max(slotHeight(hhmm(slot.start_time), hhmm(slot.end_time)), 44);
  const accent = courseAccentVar(slot.course_code as CourseCode);
  return (
    <div
      className="absolute left-1.5 right-1.5 rounded-[7px] bg-surface-2 border border-border overflow-hidden cursor-pointer transition-[border-color,background,transform] hover:border-border-strong hover:-translate-y-px"
      style={{ top, height, ["--accent" as string]: accent } as CSSProperties}
    >
      <span
        className="absolute left-0 top-0 bottom-0 w-[3px]"
        style={{ background: accent }}
      />
      <span className="absolute top-1.5 right-2 font-mono text-[10px] text-muted tracking-[0.02em]">
        {hhmm(slot.start_time)}
      </span>
      <div className="px-2 pl-3 py-1.5 pr-10 h-full flex flex-col gap-0.5 overflow-hidden">
        <div className="font-mono text-[10.5px] font-semibold tracking-[0.04em] truncate" style={{ color: accent }}>
          {slot.course_code}
          <span className="text-muted font-normal pl-1.5 ml-0.5 border-l border-hairline capitalize">
            {slot.kind}
          </span>
        </div>
        <div className="text-[12px] font-medium text-fg truncate leading-tight">
          {slot.room || "—"}
        </div>
      </div>
    </div>
  );
}

/** ISO week number — matches the design header. */
function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}
