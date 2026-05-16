import { Link, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useVerifyEmail } from "@/lib/queries";
import { Wordmark } from "@/components/brand/wordmark";
import { useDocumentTitle, useHtmlLang } from "@/lib/document-head";

export default function VerifyEmail() {
  useDocumentTitle();
  useHtmlLang();

  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const result = useVerifyEmail(token);

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-bg">
      <div className="w-full max-w-sm flex flex-col items-center">
        <div className="mb-8 flex items-center justify-center text-fg">
          <Wordmark className="h-16 md:h-20" title="OpenStudy" />
        </div>

        <div className="w-full card p-6 md:p-7 flex flex-col gap-5 shadow-xl shadow-black/20">
          <div>
            <h2 className="text-base font-semibold">Email verification</h2>
          </div>

          {!token ? (
            <p className="text-xs text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2">
              Invalid or missing verification token.
            </p>
          ) : result.isPending ? (
            <p className="text-xs text-muted flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Verifying…
            </p>
          ) : result.isError ? (
            <p className="text-xs text-critical bg-critical/10 border border-critical/30 rounded-md px-3 py-2">
              {result.error?.message ?? "Expired or invalid token. Please request a new verification email."}
            </p>
          ) : (
            <p className="text-xs text-success bg-success/10 border border-success/30 rounded-md px-3 py-2">
              {result.data?.message ?? "Your email has been verified."}{" "}
              <Link to="/login" className="underline underline-offset-2 hover:text-primary">
                Sign in
              </Link>
            </p>
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
