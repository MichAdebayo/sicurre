import { createAuthClient } from "better-auth/react";

const baseURL =
  import.meta.env.VITE_BETTER_AUTH_BASE_URL?.trim() ||
  (typeof window !== "undefined" ? `${window.location.origin}/api/auth` : "/api/auth");

export const authClient = createAuthClient({
  baseURL,
});