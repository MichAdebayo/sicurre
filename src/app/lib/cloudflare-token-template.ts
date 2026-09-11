/**
 * A Cloudflare token-creation link with Sicurre's permissions already selected.
 *
 * Cloudflare reads `permissionGroupKeys` from the token page URL and pre-ticks
 * those rows. The keys are slugs, not the UUIDs the permission-groups API
 * returns, and are not published; each one below was confirmed by opening the
 * link and checking the pre-selected rows. An unrecognised key is ignored
 * silently, so change a key only after re-testing the real link.
 */

/** Every endpoint the provisioner calls, and the permission it needs. */
export const SICURRE_TOKEN_PERMISSIONS = [
  { key: "dns", scope: "Zone", label: "DNS" },
  { key: "zone_settings", scope: "Zone", label: "Zone Settings" },
  { key: "email_routing_rule", scope: "Zone", label: "Email Routing Rules" },
  { key: "email_routing_address", scope: "Account", label: "Email Routing Addresses" },
  { key: "workers_scripts", scope: "Account", label: "Workers Scripts" },
] as const;

/**
 * Build the pre-filled link. `zoneId` stays "all" because the zone's id is not
 * known until a token exists to look it up with; the customer narrows the
 * resource in Cloudflare's own form.
 */
export function cloudflareTokenTemplateUrl(domain?: string): string {
  const permissions = SICURRE_TOKEN_PERMISSIONS.map(({ key }) => ({ key, type: "edit" }));
  const params = new URLSearchParams({
    permissionGroupKeys: JSON.stringify(permissions),
    accountId: "*",
    zoneId: "all",
    name: domain ? `Sicurre - ${domain}` : "Sicurre",
  });
  return `https://dash.cloudflare.com/profile/api-tokens?${params.toString()}`;
}
