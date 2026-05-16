import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { KeyRound, Loader2 } from "lucide-react";
import { useResetPassword } from "@/lib/queries";
import { Wordmark } from "@/components/brand/wordmark";
import { useDocumentTitle, useHtmlLang } from "@/lib/document-head";

export default function ResetPassword() {
  useDocumentTitle();
  useHtmlLang();

  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const resetPassword = useResetPassword();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    if (password !== confirm) {
      setErr("Passwords do not match.");
      return;
    }
    try {
      await resetPassword.mutateAsync({ token: token!, new_password: password });
      setSuccess(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reset failed.");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-bg">
      <div className="w-full max-w-sm flex flex-col items-center">
        <div className="mb-8 flex items-center justify-center text-fg">
          <Wordmark className="h-16 md:h-20" title="OpenStudy" />
        </div>

        <div className="w-full card p-6 md:p-7 flex flex-col gap-5 shadow-xl shadow-black/20">
          <div>
            <h2 className="text-base font-semibold">Reset password</h2>
            <p className="text-xs text-muted mt-1">
              Choose a new password for your account.
            </p>
          </div>

          {!token ? (
            <p className="text-xs text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2">
              Invalid or missing reset token. Please request a new reset link.
            </p>
          ) : success ? (
            <p className="text-xs text-success bg-success/10 border border-success/30 rounded-md px-3 py-2">
              Your password has been reset.{" "}
              <Link to="/login" className="underline underline-offset-2 hover:text-primary">
                Sign in
              </Link>
            </p>
          ) : (
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">New password</span>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
                  <input
                    type="password"
                    name="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoFocus
                    disabled={!token}
                    className="w-full bg-surface-2 border border-border/60 rounded-md pl-10 pr-3 py-2.5 text-sm text-fg placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-60"
                    placeholder="••••••••••••"
                  />
                </div>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">Confirm new password</span>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
                  <input
                    type="password"
                    name="confirm"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                    disabled={!token}
                    className="w-full bg-surface-2 border border-border/60 rounded-md pl-10 pr-3 py-2.5 text-sm text-fg placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-60"
                    placeholder="••••••••••••"
                  />
                </div>
              </label>

              {err && (
                <p className="text-xs text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2">
                  {err}
                </p>
              )}

              <button
                type="submit"
                disabled={resetPassword.isPending || !password || !confirm || !token}
                className="touch-target inline-flex items-center justify-center gap-2 rounded-md bg-primary text-primary-fg text-sm font-medium px-4 py-2.5 disabled:opacity-60 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
              >
                {resetPassword.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Resetting…
                  </>
                ) : (
                  "Reset password"
                )}
              </button>
            </form>
          )}

          <p className="text-xs text-muted text-center">
            <Link to="/login" className="text-fg underline underline-offset-2 hover:text-primary">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
