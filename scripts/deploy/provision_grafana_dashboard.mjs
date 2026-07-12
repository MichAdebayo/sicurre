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
const dashboardPath = process.env.GRAFANA_DASHBOARD_PATH ||
  path.join(rootDir, "deploy/grafana/dashboards/sicurre-runtime-overview.json");

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

async function requireDatasources() {
  const { body } = await grafanaFetch("/api/datasources");
  const availableTypes = new Set(body.map((datasource) => datasource.type));
  const requiredTypes = ["prometheus", "loki", "tempo"];
  const missingTypes = requiredTypes.filter((type) => !availableTypes.has(type));
  if (missingTypes.length > 0) {
    throw new Error(`Grafana is missing required datasources: ${missingTypes.join(", ")}`);
  }
}

const dashboard = JSON.parse(await readFile(dashboardPath, "utf8"));
dashboard.id = null;

await requireDatasources();
await ensureFolder();
const provisioned = await grafanaFetch("/api/dashboards/db", {
  method: "POST",
  body: JSON.stringify({
    dashboard,
    folderUid,
    overwrite: true,
    message: "Provision Sicurre runtime dashboard from repository",
  }),
});
const verified = await grafanaFetch(`/api/dashboards/uid/${dashboard.uid}`);
if (verified.body.dashboard?.uid !== dashboard.uid) {
  throw new Error(`Grafana dashboard verification failed for UID ${dashboard.uid}.`);
}

console.log(
  `Provisioned Grafana dashboard '${dashboard.title}' in folder '${folderTitle}': ` +
  `${grafanaUrl}${provisioned.body.url}`,
);
