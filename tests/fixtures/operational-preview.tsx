import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { OperationalExercisePanel } from "../../src/app/components/admin/operational-exercise-panel";
import "../../src/app/index.css";
import fr from "../../src/app/locales/fr.json";
import en from "../../src/app/locales/en.json";

// Local visual fixture: every request is intercepted, never forwarded to production.
const params = new URLSearchParams(location.search);
document.documentElement.classList.toggle("dark", params.get("theme") === "dark");
const state = { enabled: true, active: null as Record<string, unknown> | null, recent: [] as Record<string, unknown>[] };
window.fetch = async (_input, init) => {
  if (params.get("state") === "error") return new Response("{}", { status: 503 });
  if (init?.method === "POST") {
    if (state.active) {
      state.active.status = "recovered";
      state.active.recovered_at = new Date().toISOString();
      state.active = null;
    } else {
      state.active = { id: "local-visual-fixture", exercise_type: "api_unavailable", status: "active",
        started_at: new Date().toISOString(), expires_at: new Date(Date.now() + 240000).toISOString(),
        initiated_by: "operator@example.test", recovered_at: null };
      state.recent.unshift(state.active);
    }
  }
  return Response.json(state);
};
await i18n.use(initReactI18next).init({ resources: { fr: { translation: fr }, en: { translation: en } }, lng: params.get("lang") || "fr" });
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient()}>
    <main className="mx-auto w-full p-6" style={{ maxWidth: Number(params.get("width")) || 1024 }}><OperationalExercisePanel /></main>
  </QueryClientProvider>,
);
