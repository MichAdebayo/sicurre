#!/usr/bin/env node
import { execFileSync } from "node:child_process";

const dbPath = "data/local/sicurre.db";
const cfBase = "https://api.cloudflare.com/client/v4";

function sqliteJson(sql) {
  const out = execFileSync("sqlite3", ["-json", dbPath, sql], { encoding: "utf8" });
  return JSON.parse(out || "[]");
}

async function cfFetch(token, path) {
  const response = await fetch(`${cfBase}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const payload = await response.json().catch(() => ({}));
  return { ok: response.ok && payload.success !== false, status: response.status, payload };
}

function redactBinding(binding) {
  const value = binding.text || binding.value || "";
  return {
    name: binding.name,
    type: binding.type,
    has_value: Boolean(value),
    value_preview:
      binding.name === "SICURRE_SCAN_URL" || binding.name === "FORWARD_TO"
        ? value
        : undefined,
  };
}

async function probeScanUrl(scanUrl) {
  if (!scanUrl) return { ok: false, reason: "missing_scan_url" };
  const payload = {
    subject: "Sicurre reachability probe",
    sender: "probe@example.com",
    text: "Connectivity probe without shared secret.",
    use_llm: false,
    use_virustotal: false,
  };
  try {
    const response = await fetch(scanUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return {
      ok: true,
      status: response.status,
      expected_without_secret: response.status === 401,
      body_preview: (await response.text()).slice(0, 160),
    };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

const integrations = sqliteJson(
  "select zone_name, zone_id, account_id, worker_name, rule_id, destination_email, status from cloudflare_integration order by updated_at desc limit 1"
);
const tokenRows = sqliteJson("select api_token from app_cloudflare_config limit 1");

if (!integrations.length || !tokenRows.length) {
  console.log(JSON.stringify({ ok: false, reason: "missing_local_cloudflare_config" }, null, 2));
  process.exit(1);
}

const integration = integrations[0];
const token = tokenRows[0].api_token;
const result = {
  ok: true,
  local_integration: {
    zone_name: integration.zone_name,
    worker_name: integration.worker_name,
    rule_id: integration.rule_id,
    destination_email: integration.destination_email,
    status: integration.status,
  },
  cloudflare: {},
  scan_probe: {},
};

const zoneLookup = await cfFetch(token, `/zones?name=${encodeURIComponent(integration.zone_name)}`);
result.cloudflare.zone_lookup = {
  ok: zoneLookup.ok,
  status: zoneLookup.status,
  zone_count: zoneLookup.payload.result?.length || 0,
};

const zone = zoneLookup.payload.result?.[0];
const zoneId = zone?.id || integration.zone_id;
const accountId = zone?.account?.id || integration.account_id;

if (zoneId) {
  const routingStatus = await cfFetch(token, `/zones/${zoneId}/email/routing`);
  result.cloudflare.email_routing = {
    ok: routingStatus.ok,
    status: routingStatus.status,
    enabled: routingStatus.payload.result?.enabled,
    name: routingStatus.payload.result?.name,
  };

  const rules = await cfFetch(token, `/zones/${zoneId}/email/routing/rules`);
  const ruleList = rules.payload.result || [];
  result.cloudflare.rules = {
    ok: rules.ok,
    status: rules.status,
    count: ruleList.length,
    matching_rule: ruleList
      .filter((rule) => rule.id === integration.rule_id || rule.name?.toLowerCase().includes("sicurre"))
      .map((rule) => ({
        id: rule.id,
        name: rule.name,
        enabled: rule.enabled,
        actions: rule.actions,
        matchers: rule.matchers,
      })),
  };
}

if (accountId && integration.worker_name) {
  const settings = await cfFetch(token, `/accounts/${accountId}/workers/scripts/${integration.worker_name}/settings`);
  const bindings = settings.payload.result?.bindings || [];
  result.cloudflare.worker_settings = {
    ok: settings.ok,
    status: settings.status,
    binding_names: bindings.map((binding) => binding.name),
    visible_bindings: bindings.map(redactBinding),
  };
  const scanUrl = bindings.find((binding) => binding.name === "SICURRE_SCAN_URL")?.text;
  result.scan_probe = await probeScanUrl(scanUrl);
}

console.log(JSON.stringify(result, null, 2));
