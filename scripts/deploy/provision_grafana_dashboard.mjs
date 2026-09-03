import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { TransientError, isRetryableStatus, withRetry } from "./retry.mjs";
import { withOperationsRoutes } from "./notification-policy.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "../..");

function normalizeGrafanaUrl(value) {
  if (!value) return undefined;
  const withScheme = /^https?:\/\//i.test(value) ? value : `https://${value}`;
  return withScheme.replace(/\/$/, "");
}

const grafanaUrl = normalizeGrafanaUrl(process.env.GRAFANA_URL);
const token = process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN || process.env.GRAFANA_API_TOKEN;
const folderUid = process.env.GRAFANA_SICURRE_FOLDER_UID || "sicurre";
const folderTitle = process.env.GRAFANA_SICURRE_FOLDER_TITLE || "Sicurre";
const dashboardPaths = process.env.GRAFANA_DASHBOARD_PATH
  ? [process.env.GRAFANA_DASHBOARD_PATH]
  : [
      "sicurre-runtime-overview.json",
      "sicurre-infrastructure.json",
      "sicurre-telemetry-pipeline.json",
      "sicurre-controlled-exercise.json",
    ].map((name) => path.join(rootDir, "deploy/grafana/dashboards", name));
const alertingPath = process.env.GRAFANA_ALERTING_PATH
  || path.join(rootDir, "deploy/grafana/alerts/sicurre-alerts.json");

// A suspended free-tier instance answers 503 while it wakes. Six attempts with
// capped exponential backoff wait roughly 90s before giving up.
const retryMaxAttempts = Number(process.env.GRAFANA_PROVISION_MAX_ATTEMPTS || 6);
const retryBaseMs = Number(process.env.GRAFANA_PROVISION_RETRY_BASE_MS || 2000);
const retryMaxMs = Number(process.env.GRAFANA_PROVISION_RETRY_MAX_MS || 30000);

if (!grafanaUrl || !token) {
  console.error("GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN are required.");
  process.exit(1);
}

function parseBody(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    // A gateway or a waking instance can answer with HTML. Keep the raw text so
    // the surfaced error describes the real failure instead of a parse error.
    return { raw: text };
  }
}

async function grafanaFetch(endpoint, options = {}) {
  const method = options.method || "GET";

  return withRetry(
    async () => {
      let response;
      try {
        response = await fetch(`${grafanaUrl}${endpoint}`, {
          ...options,
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
            ...(options.headers || {}),
          },
        });
      } catch (error) {
        // DNS, connection reset, and timeouts are worth repeating.
        throw new TransientError(`${method} ${endpoint} failed: ${error.message}`, {
          cause: error,
        });
      }

      const text = await response.text();
      const body = parseBody(text);
      if (response.ok || response.status === 412) {
        return { status: response.status, body };
      }

      const message = `${method} ${endpoint} failed: ${response.status} ${text}`;
      if (isRetryableStatus(response.status)) {
        throw new TransientError(message, { status: response.status });
      }
      throw new Error(message);
    },
    {
      maxAttempts: retryMaxAttempts,
      baseMs: retryBaseMs,
      maxMs: retryMaxMs,
      onRetry: ({ attempt, maxAttempts, delayMs, error }) => {
        const wait = delayMs >= 1000 ? `${Math.round(delayMs / 1000)}s` : `${delayMs}ms`;
        console.warn(
          `Grafana call not ready (attempt ${attempt}/${maxAttempts}), `
            + `retrying in ${wait}: ${error.message}`,
        );
      },
    },
  );
}

async function ensureContactPoint(contactPoint) {
  const { body: contactPoints } = await grafanaFetch("/api/v1/provisioning/contact-points");
  const existing = contactPoints.find(
    (candidate) => candidate.uid === contactPoint.uid || candidate.name === contactPoint.name,
  );
  const endpoint = existing
    ? `/api/v1/provisioning/contact-points/${existing.uid}`
    : "/api/v1/provisioning/contact-points";
  const payload = { ...contactPoint, uid: existing?.uid || contactPoint.uid };
  await grafanaFetch(endpoint, {
    method: existing ? "PUT" : "POST",
    headers: { "X-Disable-Provenance": "true" },
    body: JSON.stringify(payload),
  });
  return payload.name;
}

function alertQuery(rule, prometheusUid) {
  return {
    title: rule.title,
    ruleGroup: "Sicurre production",
    folderUID: folderUid,
    noDataState: rule.noDataState,
    execErrState: "Error",
    for: rule.for,
    orgId: 1,
    uid: rule.uid,
    condition: "B",
    annotations: {
      summary: rule.summary,
      runbook: rule.runbook,
    },
    labels: {
      stack: "sicurre",
      severity: rule.uid.includes("controlled") ? "info" : "warning",
      managed_by: "repository",
      ...rule.labels,
    },
    isPaused: false,
    data: [
      {
        refId: "A",
        queryType: "",
        relativeTimeRange: { from: 600, to: 0 },
        datasourceUid: prometheusUid,
        model: {
          expr: rule.expression,
          hide: false,
          intervalMs: 1000,
          maxDataPoints: 43200,
          refId: "A",
        },
      },
      {
        refId: "B",
        queryType: "",
        relativeTimeRange: { from: 0, to: 0 },
        datasourceUid: "-100",
        model: {
          conditions: [
            {
              evaluator: { params: [rule.threshold], type: rule.operator },
              operator: { type: "and" },
              query: { params: ["A"] },
              reducer: { params: [], type: "last" },
              type: "query",
            },
          ],
          datasource: { type: "__expr__", uid: "-100" },
          hide: false,
          intervalMs: 1000,
          maxDataPoints: 43200,
          refId: "B",
          type: "classic_conditions",
        },
      },
    ],
  };
}

async function ensureAlertRule(rule, prometheusUid) {
  const payload = alertQuery(rule, prometheusUid);
  const existing = await grafanaFetch(`/api/v1/provisioning/alert-rules/${rule.uid}`).catch(
    () => null,
  );
  await grafanaFetch(
    existing ? `/api/v1/provisioning/alert-rules/${rule.uid}` : "/api/v1/provisioning/alert-rules",
    {
      method: existing ? "PUT" : "POST",
      headers: { "X-Disable-Provenance": "true" },
      body: JSON.stringify(payload),
    },
  );
}

async function ensureNotificationPolicy(receiver) {
  const { body: policy } = await grafanaFetch("/api/v1/provisioning/policies");
  await grafanaFetch("/api/v1/provisioning/policies", {
    method: "PUT",
    headers: { "X-Disable-Provenance": "true" },
    body: JSON.stringify(withOperationsRoutes(policy, receiver)),
  });
}

async function ensureFolder() {
  const existing = await grafanaFetch(`/api/folders/${folderUid}`).catch(() => null);
  if (existing?.status === 200) {
    return folderUid;
  }

  await grafanaFetch("/api/folders", {
    method: "POST",
    body: JSON.stringify({ uid: folderUid, title: folderTitle }),
  });
  return folderUid;
}

const datasourceNames = {
  prometheus: "grafanacloud-sicurre-prom",
  loki: "grafanacloud-sicurre-logs",
  tempo: "grafanacloud-sicurre-traces",
};

async function resolveDatasources() {
  const { body } = await grafanaFetch("/api/datasources");
  const resolved = Object.fromEntries(
    Object.entries(datasourceNames).map(([variable, name]) => [
      variable,
      body.find((datasource) => datasource.name === name),
    ]),
  );
  const missing = Object.entries(resolved)
    .filter(([, datasource]) => !datasource)
    .map(([variable]) => datasourceNames[variable]);
  if (missing.length > 0) {
    throw new Error(`Grafana is missing required datasources: ${missing.join(", ")}`);
  }
  return resolved;
}

function bindDatasources(dashboard, datasources) {
  const variables = dashboard.templating?.list || [];
  for (const variable of variables) {
    const datasource = datasources[variable.name];
    if (!datasource) continue;
    variable.current = {
      selected: true,
      text: datasource.name,
      value: datasource.uid,
    };
    variable.regex = `/^${datasource.name}$/`;
  }
}

const datasources = await resolveDatasources();
await ensureFolder();

for (const dashboardPath of dashboardPaths) {
  const dashboard = JSON.parse(await readFile(dashboardPath, "utf8"));
  dashboard.id = null;
  bindDatasources(dashboard, datasources);

  const provisioned = await grafanaFetch("/api/dashboards/db", {
    method: "POST",
    body: JSON.stringify({
      dashboard,
      folderUid,
      overwrite: true,
      message: "Provision Sicurre observability dashboards from repository",
    }),
  });
  const verified = await grafanaFetch(`/api/dashboards/uid/${dashboard.uid}`);
  if (verified.body.dashboard?.uid !== dashboard.uid) {
    throw new Error(`Grafana dashboard verification failed for UID ${dashboard.uid}.`);
  }
  for (const variable of dashboard.templating?.list || []) {
    const datasource = datasources[variable.name];
    if (!datasource) continue;
    const savedVariable = verified.body.dashboard.templating.list.find(
      (candidate) => candidate.name === variable.name,
    );
    if (savedVariable?.current?.value !== datasource.uid) {
      throw new Error(
        `Grafana datasource binding verification failed for '${variable.name}'.`,
      );
    }
  }

  console.log(
    `Provisioned Grafana dashboard '${dashboard.title}' in folder '${folderTitle}': ` +
    `${grafanaUrl}${provisioned.body.url}`,
  );
}

const alerting = JSON.parse(await readFile(alertingPath, "utf8"));
const receiver = await ensureContactPoint(alerting.contactPoint);
for (const rule of alerting.rules) {
  await ensureAlertRule(rule, datasources.prometheus.uid);
}
await ensureNotificationPolicy(receiver);

const { body: provisionedRules } = await grafanaFetch("/api/v1/provisioning/alert-rules");
const missingRuleUids = alerting.rules
  .map((rule) => rule.uid)
  .filter((uid) => !provisionedRules.some((rule) => rule.uid === uid));
if (missingRuleUids.length > 0) {
  throw new Error(`Grafana alert verification failed: ${missingRuleUids.join(", ")}`);
}
console.log(
  `Provisioned ${alerting.rules.length} Sicurre alert rules and '${receiver}' notification routing.`,
);
