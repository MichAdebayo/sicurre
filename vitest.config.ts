import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/unit/app/**/*.test.{ts,mjs}"],
    coverage: {
      provider: "v8",
      include: [
        "auth-service/server.ts",
        "scripts/app/container_server.mjs",
        "src/app/lib/schemas.ts",
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
