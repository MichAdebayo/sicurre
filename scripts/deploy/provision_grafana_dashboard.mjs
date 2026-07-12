import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
    ].map((name) => path.join(rootDir, "deploy/grafana/dashboards", name));

if (!grafanaUrl || !token) {
  console.error("GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN are required.");
  process.exit(1);
}

async function grafanaFetch(endpoint, options = {}) {
  const response = await fetch(`${grafanaUrl}${endpoint}`, {
    ...options,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok && response.status !== 412) {
    throw new Error(`${options.method || "GET"} ${endpoint} failed: ${response.status} ${text}`);
  }
  return { status: response.status, body };
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
