import { createAuthClient } from "better-auth/react";

const baseURL =
  import.meta.env.VITE_BETTER_AUTH_BASE_URL?.trim() || "/api/auth";

export const authClient = createAuthClient({
  baseURL,
});