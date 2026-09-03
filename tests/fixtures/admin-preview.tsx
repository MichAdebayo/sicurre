import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { applyTheme } from "../../src/app/lib/theme";
import type { OperationalExercise, OperationalExerciseType } from "../../src/app/lib/api";
import "../../src/app/index.css";
import fr from "../../src/app/locales/fr.json";
import en from "../../src/app/locales/en.json";

// This fixture intercepts every fetch; no customer data or production write is used.
const params = new URLSearchParams(location.search);
applyTheme(params.get("theme") === "dark" ? "dark" : "light");
const types: OperationalExerciseType[] = ["api_unavailable", "high_latency", "elevated_5xx"];
const state = {
  enabled: true, supported_types: types, active: null as OperationalExercise | null,
  recent: types.map((type, index): OperationalExercise => ({
    id: `local-history-${index}`, exercise_type: type, status: "recovered", initiated_by: "operator@example.test",
    started_at: new Date(Date.now() - (index + 1) * 3600000).toISOString(),
    expires_at: new Date(Date.now() - (index + 1) * 3600000 + 240000).toISOString(),
    recovered_at: new Date(Date.now() - (index + 1) * 3600000 + 200000).toISOString(),
  })),
};
const domains = Array.from({ length: 43 }, (_, i) => ({ zone_name: `domain-${i + 1}.example.test`, user_email: "owner@example.test", status: "active", updated_at: new Date().toISOString() }));
window.fetch = async (input, init) => {
  const url = new URL(String(input), location.origin);
  await new Promise((resolve) => setTimeout(resolve, 250));
  if (url.pathname.endsWith("/auth/session")) return Response.json({
    workspace_id: "local-workspace", display_name: "Demo Operator", email: "operator@example.test",
    role: "owner", is_platform_admin: true, onboarding_required: true,
  });
  if (url.pathname.endsWith("/integrations/cloudflare/list")) return Response.json([]);
  if (url.pathname.endsWith("/admin/runtime-health")) return Response.json({
    status: "down", checked_at: new Date().toISOString(), expected_worker_scan_url: "https://gateway.example.test/scan",
    inference_api_url: "https://inference.example.test/v1/classify", components: [
      { component: "public_app_api", status: "ok", latency_ms: 32, detail: "HTTP 200" },
      { component: "inference_api", status: "ok", latency_ms: 45, detail: "HTTP 200" },
      { component: "cloudflare_worker", status: "degraded", latency_ms: 600, detail: "Local fixture: degraded dependency" },
      { component: "quarantine_storage", status: "down", latency_ms: null, detail: "Local fixture: unavailable dependency" },
    ],
  });
  if (url.pathname.endsWith("/admin/overview")) return Response.json({
    summary: { workspaces_count: 24, threat_events_count: 1456, feedback_count: 6, false_negative_count: 2,
      reported_email_count: 1, cloudflare_active_count: 39, cloudflare_integrations_count: 43, support_open_count: 3 },
    verdicts: [{ verdict: "legitimate", count: 920 }, { verdict: "spam", count: 412 }, { verdict: "phishing", count: 124 }],
    recent_feedback: [{ id: "feedback-1", feedback_type: "false_positive", original_verdict: "phishing", corrected_verdict: "legitimate", created_at: new Date().toISOString(), reporter_email: "owner@example.test" }],
    recent_quarantine: [{ id: "quarantine-1", safety_verdict: "phishing", composite_score: 0.92, status: "held", expires_at: new Date().toISOString() }],
    recent_support: [{ id: "support-1", category: "dns", status: "open", requester_email: "owner@example.test", created_at: new Date().toISOString() }],
  });
  if (url.pathname.endsWith("/admin/domains")) {
    const page = Number(url.searchParams.get("page") || 1);
    const matches = domains.filter((domain) => domain.zone_name.includes(url.searchParams.get("search") || ""));
    return Response.json({ items: matches.slice((page - 1) * 20, page * 20), total: matches.length, pages: Math.ceil(matches.length / 20), page, page_size: 20 });
  }
  if (url.pathname.endsWith("/operational-exercises")) {
    if (init?.method === "POST") {
      if (state.active) return Response.json({ detail: "Exercise already active" }, { status: 409 });
      state.active = { id: `local-test-${Date.now()}`, exercise_type: JSON.parse(String(init.body)).exercise_type,
        initiated_by: "operator@example.test", status: "active", started_at: new Date().toISOString(), expires_at: new Date(Date.now() + 240000).toISOString() };
      state.recent.unshift(state.active);
      return Response.json(state.active);
    }
    return params.get("state") === "error" ? Response.json({}, { status: 503 }) : Response.json(state);
  }
  if (url.pathname.endsWith("/recover") && init?.method === "POST" && state.active) {
    const recovered = { ...state.active, status: "recovered" as const, recovered_at: new Date().toISOString() };
    state.recent = state.recent.map((item) => item.id === recovered.id ? recovered : item);
    state.active = null;
    return Response.json(recovered);
  }
  return Response.json({ detail: "Not available in local UI fixture" }, { status: 404 });
};
await i18n.use(initReactI18next).init({ resources: { fr: { translation: fr }, en: { translation: en } }, lng: params.get("lang") || "fr" });
window.history.replaceState({}, "", params.get("route") || "/admin/operations");
const { default: App } = await import("../../src/app/App");
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <App />
  </QueryClientProvider>,
);
