import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/unit/app/**/*.test.{ts,tsx,mjs}"],
    coverage: {
      provider: "v8",
      include: [
        "auth-service/server.ts",
        "scripts/app/container_server.mjs",
        "src/app/lib/schemas.ts",
        "src/app/components/common/app-shell.tsx",
        "src/app/components/common/app-toast.tsx",
        "src/app/components/common/sidebar.tsx",
      ],
      reporter: ["text", "json-summary", "lcov"],
      reportsDirectory: "coverage/javascript",
      thresholds: {
        lines: 90,
        functions: 90,
        statements: 90,
        branches: 80,
      },
    },
  },
});
