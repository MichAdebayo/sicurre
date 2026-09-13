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
      // Measured on 13 September 2026: lines 96%, statements 95%, branches 91%,
      // functions 94%. The floors sit a few points under so the gate bites on a
      // regression and still leaves room to work.
      thresholds: {
        lines: 90,
        statements: 90,
        branches: 85,
        functions: 90,
      },
    },
  },
});
