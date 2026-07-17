export type AdminSeedConfig = {
  email?: string;
  password?: string;
  name?: string;
};

export type AdminSeedAdapter = {
  exists(email: string): Promise<boolean>;
  create(input: { email: string; password: string; name: string }): Promise<void>;
  normalize(input: { email: string; name: string }): Promise<void>;
};

export type AdminSeedResult = "disabled" | "created" | "existing";

export async function ensureConfiguredAdmin(
  config: AdminSeedConfig,
  adapter: AdminSeedAdapter,
): Promise<AdminSeedResult> {
  const email = config.email?.trim().toLowerCase() ?? "";
  const password = config.password ?? "";
  const name = config.name?.trim() ?? "";
  const configuredValues = [email, password, name].filter(Boolean).length;

  if (configuredValues === 0) return "disabled";
  if (configuredValues !== 3) {
    throw new Error(
      "Admin seed requires SICURRE_ADMIN_EMAIL, SICURRE_ADMIN_PASSWORD, and SICURRE_ADMIN_NAME.",
    );
  }
  if (!email.includes("@")) throw new Error("SICURRE_ADMIN_EMAIL must be a valid email address.");
  if (password.length < 8) {
    throw new Error("SICURRE_ADMIN_PASSWORD must contain at least 8 characters.");
  }

  const existing = await adapter.exists(email);
  if (!existing) await adapter.create({ email, password, name });
  await adapter.normalize({ email, name });
  return existing ? "existing" : "created";
}
