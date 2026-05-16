import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Loader2, Mail } from "lucide-react";
import { useForgotPassword } from "@/lib/queries";
import { Wordmark } from "@/components/brand/wordmark";
import { useDocumentTitle, useHtmlLang } from "@/lib/document-head";

export default function ForgotPassword() {
  useDocumentTitle();
  useHtmlLang();

  const forgotPassword = useForgotPassword();
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    try {
      await forgotPassword.mutateAsync({ email });
      setSuccess(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Request failed.");
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
            <h2 className="text-base font-semibold">Forgot password</h2>
            <p className="text-xs text-muted mt-1">
              Enter your email and we will send you a reset link.
            </p>
          </div>

          {success ? (
            <p className="text-xs text-success bg-success/10 border border-success/30 rounded-md px-3 py-2">
              If that email exists, a reset link has been sent. Check your inbox.
            </p>
          ) : (
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">Email</span>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
                  <input
                    type="email"
                    name="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoFocus
                    className="w-full bg-surface-2 border border-border/60 rounded-md pl-10 pr-3 py-2.5 text-sm text-fg placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
                    placeholder="you@example.com"
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
                disabled={forgotPassword.isPending || !email}
                className="touch-target inline-flex items-center justify-center gap-2 rounded-md bg-primary text-primary-fg text-sm font-medium px-4 py-2.5 disabled:opacity-60 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
              >
                {forgotPassword.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Sending…
                  </>
                ) : (
                  "Send reset link"
                )}
              </button>
            </form>
          )}

          <p className="text-xs text-muted text-center">
            Remember your password?{" "}
            <Link to="/login" className="text-fg underline underline-offset-2 hover:text-primary">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
