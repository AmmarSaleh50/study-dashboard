import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { KeyRound, Loader2, Mail, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLogin, useSession } from "@/lib/queries";
import { ApiError } from "@/lib/api";
import { Wordmark } from "@/components/brand/wordmark";
import { useDocumentTitle, useHtmlLang } from "@/lib/document-head";

export default function Login() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const login = useLogin();

  useDocumentTitle();
  useHtmlLang();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const next = new URLSearchParams(location.search).get("next") ?? "/app";

  if (session.data?.authed) {
    return <Navigate to={next} replace />;
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    try {
      await login.mutateAsync({ email: email || undefined, password, totp_code: needsTotp ? totpCode : undefined });
      if (next.startsWith("/oauth") || next.startsWith("/mcp") || next.startsWith("/.well-known")) {
        window.location.href = next;
      } else {
        navigate(next, { replace: true });
      }
    } catch (e) {
      if (e instanceof ApiError) {
        // ApiError.detail is unwrapped: when FastAPI returns {"detail": "x"},
        // detail is the string "x" (not an object).
        const detailStr = typeof e.detail === "string"
          ? e.detail
          : (e.detail as { detail?: string } | undefined)?.detail;
        if (e.status === 429) {
          setErr(t("login.tooMany", "Too many attempts. Try again in a few minutes."));
        } else if (e.status === 401 && detailStr === "totp_required") {
          setNeedsTotp(true);
          setErr(null);
        } else if (e.status === 401 && detailStr === "invalid totp code") {
          setErr(t("login.totpWrong", "Wrong 6-digit code. Try again."));
          setTotpCode("");
        } else if (e.status === 401) {
          setErr(t("login.wrong"));
          setNeedsTotp(false);
          setTotpCode("");
        } else {
          setErr(e.message);
        }
      } else {
        setErr(t("common.failed"));
      }
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-bg">
      <div className="w-full max-w-sm flex flex-col items-center">
        <div className="mb-8 flex items-center justify-center text-fg">
          <Wordmark className="h-16 md:h-20" title={t("login.brand", "OpenStudy")} />
        </div>

        <div className="w-full card p-6 md:p-7 flex flex-col gap-5 shadow-xl shadow-black/20">
          <div>
            <h2 className="text-base font-semibold">{t("login.title")}</h2>
            <p className="text-xs text-muted mt-1">
              {t("login.intro", "Enter your email and password to continue.")}
            </p>
          </div>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted">{t("login.email", "Email")}</span>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus={!needsTotp}
                  disabled={needsTotp}
                  className="w-full bg-surface-2 border border-border/60 rounded-md pl-10 pr-3 py-2.5 text-sm text-fg placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-60"
                  placeholder="you@example.com"
                />
              </div>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted">{t("login.password")}</span>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
                <input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={needsTotp}
                  className="w-full bg-surface-2 border border-border/60 rounded-md pl-10 pr-3 py-2.5 text-sm text-fg placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-60"
                  placeholder="••••••••••••"
                />
              </div>
            </label>

            {needsTotp && (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">{t("login.totp", "6-digit code from your authenticator")}</span>
                <div className="relative">
                  <ShieldCheck className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    autoComplete="one-time-code"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                    required
                    autoFocus
                    className="w-full bg-surface-2 border border-border/60 rounded-md pl-10 pr-3 py-2.5 text-sm tracking-[0.3em] text-fg placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
                    placeholder="123456"
                  />
                </div>
              </label>
            )}

            {err && (
              <p className="text-xs text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2">
                {err}
              </p>
            )}

            <button
              type="submit"
              disabled={login.isPending || !email || !password}
              className="touch-target inline-flex items-center justify-center gap-2 rounded-md bg-primary text-primary-fg text-sm font-medium px-4 py-2.5 disabled:opacity-60 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
            >
              {login.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> {t("login.signingIn", "Signing in…")}
                </>
              ) : (
                t("login.submit")
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
