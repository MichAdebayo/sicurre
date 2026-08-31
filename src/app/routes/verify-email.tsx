import { useEffect, useRef } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import sicurreLogo from "../assets/sicurre.svg";
import { authBaseURL } from "../lib/auth-client";
import { verifyEmailFromLink } from "../lib/email-verification";

interface VerifyEmailRouteProps {
  onNavigateToLogin: () => void;
}

function readFragmentToken(): string {
  return new URLSearchParams(window.location.hash.slice(1)).get("token")?.trim() ?? "";
}

export default function VerifyEmailRoute({ onNavigateToLogin }: VerifyEmailRouteProps) {
  const { t } = useTranslation();
  const token = readFragmentToken();
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verifyEmailFromLink(token, window.location.origin, authBaseURL);
  }, [token]);

  if (token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-low px-5 text-on-surface">
        <p role="status" className="text-sm font-semibold">{t("verify_email.verifying")}</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-surface-low px-5 py-10 text-on-surface">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-lg items-center">
        <section className="w-full rounded-lg border border-border-subtle bg-surface-lowest p-7 shadow-sm sm:p-10">
          <img src={sicurreLogo} alt="Sicurre" className="mb-8 h-12 w-12" />
          <h1 className="text-2xl font-bold text-on-surface">
            {t("verify_email.invalid_title")}
          </h1>
          <p className="mt-3 text-base leading-relaxed text-on-surface-variant">
            {t("verify_email.invalid_link")}
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onNavigateToLogin}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-semibold text-on-surface-variant hover:bg-surface-container"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              {t("verify_email.back_to_login")}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
