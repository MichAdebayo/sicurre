import { describe, expect, it, vi } from "vitest";

import { ensureConfiguredAdmin } from "../../../auth-service/admin-seed.js";

function adapter(existing = false) {
  return {
    exists: vi.fn(async () => existing),
    create: vi.fn(async () => undefined),
    normalize: vi.fn(async () => undefined),
  };
}

describe("production admin seed", () => {
  it("is disabled when no seed values are configured", async () => {
    const target = adapter();

    await expect(ensureConfiguredAdmin({}, target)).resolves.toBe("disabled");
    expect(target.exists).not.toHaveBeenCalled();
  });

  it("rejects partial or weak seed configuration", async () => {
    await expect(
      ensureConfiguredAdmin({ email: "owner@sicurre.com" }, adapter()),
    ).rejects.toThrow("requires SICURRE_ADMIN_EMAIL");
    await expect(
      ensureConfiguredAdmin(
        { email: "invalid", password: "long-enough", name: "Owner" },
        adapter(),
      ),
    ).rejects.toThrow("valid email address");
    await expect(
      ensureConfiguredAdmin(
        { email: "owner@sicurre.com", password: "short", name: "Owner" },
        adapter(),
      ),
    ).rejects.toThrow("at least 8 characters");
  });

  it("creates and normalizes a missing administrator", async () => {
    const target = adapter(false);

    await expect(
      ensureConfiguredAdmin(
        { email: " Owner@Sicurre.com ", password: "valid-password", name: " Owner " },
        target,
      ),
    ).resolves.toBe("created");
    expect(target.create).toHaveBeenCalledWith({
      email: "owner@sicurre.com",
      password: "valid-password",
      name: "Owner",
    });
    expect(target.normalize).toHaveBeenCalledWith({
      email: "owner@sicurre.com",
      name: "Owner",
    });
  });

  it("normalizes an existing administrator without replacing its password", async () => {
    const target = adapter(true);

    await expect(
      ensureConfiguredAdmin(
        { email: "owner@sicurre.com", password: "valid-password", name: "Owner" },
        target,
      ),
    ).resolves.toBe("existing");
    expect(target.create).not.toHaveBeenCalled();
    expect(target.normalize).toHaveBeenCalledOnce();
  });
});
