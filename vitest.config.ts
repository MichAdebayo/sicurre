import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/unit/app/**/*.test.{ts,tsx,mjs}"],
    coverage: {
      provider: "v8",
      // The whole front, the auth sidecar and the container server. Every file
      // counts, tested or not, so the figure is the one a reader of this file
      // expects rather than a hand-picked scope.
      all: true,
      include: [
        "auth-service/server.ts",
        "scripts/app/container_server.mjs",
        "src/app/**/*.{ts,tsx}",
      ],
      exclude: ["src/app/**/*.d.ts"],
      reporter: ["text", "json-summary", "lcov"],
      reportsDirectory: "coverage/javascript",
      // Measured on 13 September 2026: lines 65%, statements 63%, branches 66%,
      // functions 57%. The floors sit just under those so the gate bites on a
      // regression without pretending the front is at 90%.
      thresholds: {
        lines: 60,
        statements: 60,
        branches: 60,
        functions: 50,
      },
    },
  },
});
