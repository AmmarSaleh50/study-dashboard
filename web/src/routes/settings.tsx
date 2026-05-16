import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CalendarDays,
  Check,
  ChevronRight,
  Database,
  Loader2,
  LogOut,
  Palette,
  RefreshCw,
  Send,
  ShieldCheck,
  User,
} from "lucide-react";
import { TotpCard } from "@/components/settings/totp-card";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input, Field } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LOCALE_OPTIONS, TIMEZONE_OPTIONS } from "@/lib/locale-options";
import { THEMES, applyTheme, normalizeTheme } from "@/lib/themes";
import {
  currentLanguage,
  markLanguageExplicit,
  setLanguage,
  type AppLanguage,
} from "@/lib/i18n";
import { cn } from "@/lib/cn";
import {
  useAppSettings,
  useDashboard,
  useLogout,
  useSecretsStatus,
  useTelegramTest,
  useUpdateAppSettings,
  useUpdateSecrets,
} from "@/lib/queries";
import { fmtBerlin } from "@/lib/time";

export default function Settings() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const logout = useLogout();
  const qc = useQueryClient();
  const dashboard = useDashboard();

  async function onLogout() {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  }

  async function onRefresh() {
    await qc.invalidateQueries();
    toast.success(t("settings.data.refreshed"));
  }

  return (
    <>
      <Header title={t("settings.title")} />
      <div className="px-4 md:px-8 py-4 md:py-6 max-w-[720px] mx-auto w-full flex flex-col gap-4">
        <Section icon={<User className="h-4 w-4" />} title={t("settings.sections.profile")}>
          <ProfileForm />
        </Section>

        <Section icon={<CalendarDays className="h-4 w-4" />} title={t("settings.sections.semester")}>
          <SemesterForm />
          <div className="mt-4 pt-3 border-t border-border/50 text-sm text-muted font-mono tabular-nums">
            {t("settings.serverTime")} ·{" "}
            {dashboard.data ? fmtBerlin(dashboard.data.now, "EEE d MMM yyyy · HH:mm") : "—"}
          </div>
        </Section>

        <Section icon={<Palette className="h-4 w-4" />} title={t("settings.sections.theme")}>
          <ThemePicker />
        </Section>

        <Section icon={<Database className="h-4 w-4" />} title={t("settings.sections.data")}>
          <p className="text-sm text-muted mb-3">{t("settings.data.body")}</p>
          <Button onClick={onRefresh} variant="secondary">
            <RefreshCw className="h-4 w-4" /> {t("settings.data.refresh")}
          </Button>
        </Section>

        <Section icon={<Activity className="h-4 w-4" />} title={t("settings.sections.activity")}>
          <p className="text-sm text-muted mb-3">{t("settings.activity.body")}</p>
          <Link
            to="/app/activity"
            className="inline-flex items-center gap-2 rounded-md border border-border/60 bg-surface-2 hover:bg-surface-2/80 px-3 py-2 text-sm font-medium transition-colors"
          >
            {t("settings.activity.openLog")} <ChevronRight className="h-4 w-4" />
          </Link>
        </Section>

        <Section icon={<ShieldCheck className="h-4 w-4" />} title={t("settings.sections.security", "Security")}>
          <TotpCard />
        </Section>

        <Section icon={<Send className="h-4 w-4" />} title={t("settings.sections.telegram", "Telegram")}>
          <TelegramCard />
        </Section>

        <Section icon={<LogOut className="h-4 w-4" />} title={t("settings.sections.session")}>
          <Button onClick={onLogout} disabled={logout.isPending} variant="secondary">
            <LogOut className="h-4 w-4" /> {t("settings.session.signOut")}
          </Button>
        </Section>
      </div>
    </>
  );
}

function ProfileForm() {
  const { t } = useTranslation();
  const settings = useAppSettings();
  const update = useUpdateAppSettings();

  const [displayName, setDisplayName] = useState("");
  const [institution, setInstitution] = useState("");

  useEffect(() => {
    if (settings.data) {
      setDisplayName(settings.data.display_name ?? "");
      setInstitution(settings.data.institution ?? "");
    }
  }, [settings.data]);

  async function onSave() {
    try {
      await update.mutateAsync({
        display_name: displayName.trim() || null,
        institution: institution.trim() || null,
      });
      toast.success(t("common.saved"));
    } catch (e) {
      toast.error((e as Error).message || t("common.failed"));
    }
  }

  if (settings.isPending) {
    return <Loader2 className="h-4 w-4 animate-spin text-muted" />;
  }

  const isDirty = Boolean(
    settings.data &&
      ((displayName.trim() || null) !== (settings.data.display_name ?? null) ||
        (institution.trim() || null) !== (settings.data.institution ?? null))
  );

  return (
    <div className="flex flex-col gap-3">
      <Field label={t("settings.profile.displayName")} hint={t("settings.profile.displayNameHint")}>
        <Input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder={t("settings.profile.displayNamePlaceholder")}
        />
      </Field>
      <Field label={t("settings.profile.institution")} hint={t("settings.profile.institutionHint")}>
        <Input
          value={institution}
          onChange={(e) => setInstitution(e.target.value)}
          placeholder={t("settings.profile.institutionPlaceholder")}
        />
      </Field>
      <LanguagePicker />
      <div className="flex justify-end">
        <Button onClick={onSave} disabled={!isDirty || update.isPending}>
          {update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : t("settings.profile.saveProfile")}
        </Button>
      </div>
    </div>
  );
}

function LanguagePicker() {
  const { t, i18n } = useTranslation();
  // Re-render on language change by reading i18n.language each render.
  void i18n.language;
  const current = currentLanguage();

  function onChange(v: string) {
    const lang = (v === "de" ? "de" : "en") as AppLanguage;
    markLanguageExplicit();
    setLanguage(lang);
  }

  return (
    <Field label={t("settings.language.title")}>
      <Select value={current} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="en">{t("settings.language.english")}</SelectItem>
          <SelectItem value="de">{t("settings.language.german")}</SelectItem>
        </SelectContent>
      </Select>
    </Field>
  );
}

function nearestLocale(detected: string): string {
  if (LOCALE_OPTIONS.find((o) => o.value === detected)) return detected;
  const lang = detected.split("-")[0];
  const langMatch = LOCALE_OPTIONS.find((o) => o.value.split("-")[0] === lang);
  return langMatch?.value ?? "en-US";
}

function detectSystem() {
  let tz = "UTC";
  let loc = "en-US";
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    /* ignore */
  }
  try {
    loc = nearestLocale(navigator.language || "en-US");
  } catch {
    /* ignore */
  }
  return { tz, loc };
}

function SemesterForm() {
  const { t } = useTranslation();
  const settings = useAppSettings();
  const update = useUpdateAppSettings();

  const [label, setLabel] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [locale, setLocale] = useState("en-US");

  useEffect(() => {
    if (settings.data) {
      const { tz, loc } = detectSystem();
      setLabel(settings.data.semester_label ?? "");
      setStart(settings.data.semester_start ?? "");
      setEnd(settings.data.semester_end ?? "");
      setTimezone(settings.data.timezone ?? tz);
      setLocale(settings.data.locale ?? loc);
    }
  }, [settings.data]);

  // Auto-saves the picker/date fields. The label is the only field that
  // requires an explicit save (it's free text, you don't want to fire a request
  // on every keystroke).
  async function autoSave(patch: Record<string, unknown>) {
    try {
      await update.mutateAsync(patch);
      toast.success(t("common.saved"), { duration: 1200 });
    } catch (e) {
      toast.error((e as Error).message || t("common.failed"));
    }
  }

  async function onSaveLabel() {
    try {
      await update.mutateAsync({ semester_label: label.trim() || null });
      toast.success(t("common.saved"), { duration: 1200 });
    } catch (e) {
      toast.error((e as Error).message || t("common.failed"));
    }
  }

  const labelDirty = Boolean(
    settings.data &&
      (label.trim() || null) !== (settings.data.semester_label ?? null)
  );

  return (
    <div className="flex flex-col gap-3">
      <Field label={t("settings.semester.label")} hint={t("settings.semester.labelHint")}>
        <div className="relative">
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && labelDirty) {
                e.preventDefault();
                onSaveLabel();
              }
            }}
            placeholder={t("settings.semester.labelPlaceholder")}
            className={labelDirty ? "pr-16" : undefined}
          />
          {labelDirty && (
            <button
              type="button"
              onClick={onSaveLabel}
              disabled={update.isPending}
              className="absolute right-1 top-1/2 -translate-y-1/2 text-xs font-medium text-fg bg-surface-2 hover:bg-surface px-2.5 py-1.5 rounded-md transition-colors disabled:opacity-50"
            >
              {update.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                t("settings.semester.saveLabel")
              )}
            </button>
          )}
        </div>
      </Field>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label={t("settings.semester.startDate")} hint={t("settings.semester.startDateHint")}>
          <Input
            type="date"
            value={start}
            onChange={(e) => {
              setStart(e.target.value);
              autoSave({ semester_start: e.target.value || null });
            }}
          />
        </Field>
        <Field label={t("settings.semester.endDate")}>
          <Input
            type="date"
            value={end}
            onChange={(e) => {
              setEnd(e.target.value);
              autoSave({ semester_end: e.target.value || null });
            }}
          />
        </Field>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label={t("settings.semester.timezone")}>
          <Select
            value={timezone}
            onValueChange={(v) => {
              setTimezone(v);
              autoSave({ timezone: v });
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder={t("settings.semester.timezone")} />
            </SelectTrigger>
            <SelectContent className="max-h-[60vh]">
              {TIMEZONE_OPTIONS.map((tz) => (
                <SelectItem key={tz} value={tz}>
                  {tz}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label={t("settings.semester.dateFormat")}>
          <Select
            value={locale}
            onValueChange={(v) => {
              setLocale(v);
              autoSave({ locale: v });
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder={t("settings.semester.dateFormat")} />
            </SelectTrigger>
            <SelectContent className="max-h-[60vh]">
              {LOCALE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>
    </div>
  );
}

function ThemePicker() {
  const { t: tr } = useTranslation();
  const settings = useAppSettings();
  const update = useUpdateAppSettings();
  const current = normalizeTheme(settings.data?.theme);

  async function pick(id: string) {
    if (id === current) return;
    // Apply instantly so the UI reflects the choice; the API round-trip
    // persists it but doesn't need to block the visual change.
    applyTheme(id);
    try {
      await update.mutateAsync({ theme: id });
      toast.success(tr("common.saved"), { duration: 1200 });
    } catch (e) {
      // Roll back to the previous theme on failure.
      applyTheme(current);
      toast.error((e as Error).message || tr("common.failed"));
    }
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {THEMES.map((themeMeta) => {
        const selected = themeMeta.id === current;
        return (
          <button
            key={themeMeta.id}
            type="button"
            onClick={() => pick(themeMeta.id)}
            disabled={update.isPending}
            className={cn(
              "text-left rounded-md border px-3 py-2.5 transition-colors",
              selected
                ? "border-fg bg-surface-2"
                : "border-border/60 hover:border-border-strong hover:bg-surface-2/60"
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">
                {tr(`themes.list.${themeMeta.id}`, themeMeta.label)}
              </span>
              {selected && <Check className="h-4 w-4 text-fg" />}
            </div>
            <p className="text-xs text-muted mt-0.5">
              {tr(`themes.tagline.${themeMeta.id}`, themeMeta.tagline)}
            </p>
          </button>
        );
      })}
    </div>
  );
}

function TelegramCard() {
  const { t } = useTranslation();
  const status = useSecretsStatus();
  const update = useUpdateSecrets();
  const test = useTelegramTest();

  // Inputs start empty; the saved-state lives server-side (we only know
  // booleans via /api/settings/secrets). The user re-types only to change.
  // For chat_id we DO hydrate from the GET (it isn't secret).
  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");

  useEffect(() => {
    if (status.data) {
      setChatId(status.data.telegram_chat_id ?? "");
    }
  }, [status.data]);

  if (status.isPending) {
    return <Loader2 className="h-4 w-4 animate-spin text-muted" />;
  }

  const tokenSet = Boolean(status.data?.telegram_bot_token_set);
  const webhookSet = Boolean(status.data?.telegram_webhook_secret_set);
  const savedChatId = status.data?.telegram_chat_id ?? "";

  // Dirty detection: only send fields the user actually edited.
  // - For password fields (token, webhook): non-empty input → set; user cannot "clear" via this UI
  //   without a separate affordance, so empty input means "leave alone".
  // - For chat_id: differs from saved value → set/clear.
  const tokenDirty = botToken !== "";
  const webhookDirty = webhookSecret !== "";
  const chatIdDirty = chatId.trim() !== savedChatId;
  const isDirty = tokenDirty || webhookDirty || chatIdDirty;

  async function onSave() {
    const patch: { telegram_bot_token?: string; telegram_chat_id?: string; telegram_webhook_secret?: string } = {};
    if (tokenDirty) patch.telegram_bot_token = botToken;
    if (webhookDirty) patch.telegram_webhook_secret = webhookSecret;
    if (chatIdDirty) patch.telegram_chat_id = chatId.trim();
    try {
      await update.mutateAsync(patch);
      // Clear password fields so they don't sit in DOM after save.
      setBotToken("");
      setWebhookSecret("");
      toast.success(t("settings.telegram.saved"));
    } catch (e) {
      toast.error((e as Error).message || t("common.failed"));
    }
  }

  async function onTest() {
    try {
      const r = await test.mutateAsync();
      if (r.ok) {
        toast.success(t("settings.telegram.testSent"));
      } else {
        toast.error(t("settings.telegram.testFailed", { error: r.message ?? "" }));
      }
    } catch (e) {
      toast.error((e as Error).message || t("common.failed"));
    }
  }

  const canTest = tokenSet && Boolean(savedChatId);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted">{t("settings.telegram.intro")}</p>

      <Field label={t("settings.telegram.botToken")} hint={t("settings.telegram.botTokenHint")}>
        <div className="flex items-center gap-2">
          <Input
            type="password"
            autoComplete="new-password"
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder={tokenSet ? t("settings.telegram.placeholderUnchanged") : "123456:ABC-…"}
          />
          <StatusBadge isSet={tokenSet} t={t} />
        </div>
      </Field>

      <Field label={t("settings.telegram.chatId")} hint={t("settings.telegram.chatIdHint")}>
        <div className="flex items-center gap-2">
          <Input
            type="text"
            inputMode="numeric"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder="123456789"
          />
          <StatusBadge isSet={Boolean(savedChatId)} t={t} />
        </div>
      </Field>

      <Field label={t("settings.telegram.webhookSecret")} hint={t("settings.telegram.webhookSecretHint")}>
        <div className="flex items-center gap-2">
          <Input
            type="password"
            autoComplete="new-password"
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            placeholder={webhookSet ? t("settings.telegram.placeholderUnchanged") : ""}
          />
          <StatusBadge isSet={webhookSet} t={t} />
        </div>
      </Field>

      <div className="flex justify-end gap-2 flex-wrap">
        {canTest && (
          <Button variant="secondary" onClick={onTest} disabled={test.isPending}>
            {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {t("settings.telegram.sendTest")}
          </Button>
        )}
        <Button onClick={onSave} disabled={!isDirty || update.isPending}>
          {update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : t("settings.telegram.save")}
        </Button>
      </div>
    </div>
  );
}

function StatusBadge({ isSet, t }: { isSet: boolean; t: (k: string) => string }) {
  return (
    <span
      className={cn(
        "shrink-0 text-[11px] font-medium px-2 py-1 rounded-md border",
        isSet
          ? "border-ok/40 bg-ok/10 text-ok"
          : "border-border/60 bg-surface-2 text-subtle"
      )}
    >
      {isSet ? t("settings.telegram.set") : t("settings.telegram.notSet")}
    </span>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-4 md:p-5">
      <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted mb-3">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}
