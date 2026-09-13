// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthFlowError,
  getStoredAuthProvider,
  persistSession,
  seedStoredSession,
  useChangePassword,
  useCurrentSession,
  useDiscardSessionCache,
  useLogin,
  useLogout,
  useSignup,
  useUpdateProfile,
  type AuthSession,
} from "../../../src/app/lib/api";

const auth = vi.hoisted(() => ({
  signIn: vi.fn(),
  signUp: vi.fn(),
  changePassword: vi.fn(),
}));

vi.mock("../../../src/app/lib/auth-client", () => ({
  authBaseURL: "/api/auth",
  authClient: {
    signIn: { email: auth.signIn },
    signUp: { email: auth.signUp },
    changePassword: auth.changePassword,
  },
}));

const fetchMock = vi.fn();
let client: QueryClient;

function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const respondWith = (body: unknown, status = 200) => {
  fetchMock.mockImplementation(async () => jsonResponse(body, status));
};

const session: AuthSession = {
  id: "u-1",
  email: "michael@vinse.app",
  display_name: "Michael Adebayo",
  role: "owner",
  workspace_id: "ws-1",
  workspace_name: "Vinse",
  is_platform_admin: false,
  has_cloudflare_integration: true,
  threat_count: 3,
  onboarding_required: false,
  sla_latency_ms: 2000,
};

function request(index = 0) {
  const [url, init] = fetchMock.mock.calls[index] as [string, RequestInit];
  const headers = init.headers as Headers;
  return {
    url,
    method: init.method,
    body: init.body,
    credentials: init.credentials,
    contentType: headers instanceof Headers ? headers.get("Content-Type") : (headers as Record<string, string>)["Content-Type"],
  };
}

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  client.clear();
  localStorage.clear();
  sessionStorage.clear();
  fetchMock.mockReset();
  auth.signIn.mockReset();
  auth.signUp.mockReset();
  auth.changePassword.mockReset();
  vi.unstubAllGlobals();
});

describe("the JSON request helper, observed through the session query", () => {
  it("sends the cookie and a JSON content type to the versioned API path", async () => {
    respondWith(session);

    const { result } = renderHook(() => useCurrentSession(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.data).toEqual(session));
    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/auth/session",
      credentials: "include",
      contentType: "application/json",
    }));
  });

  it("throws the detail of the API error body when the response is not successful", async () => {
    respondWith({ detail: "Session expirée" }, 401);

    const { result } = renderHook(() => useCurrentSession(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Session expirée");
  });

  it("falls back to a generic message when the error body carries no detail", async () => {
    respondWith({ error: "boom" }, 500);

    const { result } = renderHook(() => useCurrentSession(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Request failed");
  });

  it("falls back to a generic message when the error body is not JSON at all", async () => {
    fetchMock.mockImplementation(async () => new Response("<html>Bad gateway</html>", { status: 502 }));

    const { result } = renderHook(() => useCurrentSession(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Request failed");
  });

  it("does not ask for the session while the query is disabled", () => {
    const { result } = renderHook(() => useCurrentSession(false), { wrapper: Wrapper });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();
  });
});

describe("stored session helpers", () => {
  it("defaults the auth provider to password when nothing was stored", () => {
    expect(getStoredAuthProvider()).toBe("password");
  });

  it("seeds only the fields that were given and records the provider", () => {
    seedStoredSession({ email: "michael@vinse.app", authProvider: "google" });

    expect(localStorage.getItem("sicurre_user_email")).toBe("michael@vinse.app");
    expect(localStorage.getItem("sicurre_user_name")).toBeNull();
    expect(localStorage.getItem("sicurre_user_role")).toBeNull();
    expect(getStoredAuthProvider()).toBe("google");
  });

  it("seeds every identity field when all of them are given", () => {
    seedStoredSession({ displayName: "Michael", email: "michael@vinse.app", role: "owner" });

    expect(localStorage.getItem("sicurre_user_name")).toBe("Michael");
    expect(localStorage.getItem("sicurre_user_role")).toBe("owner");
    expect(getStoredAuthProvider()).toBe("password");
  });

  it("persists the session under the provider that was already stored", () => {
    seedStoredSession({ authProvider: "google" });

    persistSession(session);

    expect(localStorage.getItem("sicurre_user_name")).toBe("Michael Adebayo");
    expect(localStorage.getItem("sicurre_user_email")).toBe("michael@vinse.app");
    expect(localStorage.getItem("sicurre_user_role")).toBe("owner");
    expect(localStorage.getItem("sicurre_auth_provider")).toBe("google");
  });
});

describe("useDiscardSessionCache", () => {
  it("clears every cached query of the tree it was rendered in", () => {
    client.setQueryData(["auth-session"], session);

    const { result } = renderHook(() => useDiscardSessionCache(), { wrapper: Wrapper });
    result.current();

    expect(client.getQueryData(["auth-session"])).toBeUndefined();
  });
});

describe("useLogin", () => {
  it("signs in with the provider, then loads and persists the API session", async () => {
    auth.signIn.mockResolvedValue({ data: { user: { id: "u-1" } }, error: null });
    respondWith(session);
    const invalidate = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useLogin(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.mutateAsync({ email: "michael@vinse.app", password: "hunter2hunter2" });
    });

    expect(auth.signIn).toHaveBeenCalledWith({ email: "michael@vinse.app", password: "hunter2hunter2" });
    expect(request().url).toBe("/v1/auth/session");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["auth-session"] });
    expect(client.getQueryData(["auth-session"])).toEqual(session);
    expect(localStorage.getItem("sicurre_auth_provider")).toBe("password");
    expect(localStorage.getItem("sicurre_user_email")).toBe("michael@vinse.app");
    expect(localStorage.getItem("sicurre_user_name")).toBe("Michael Adebayo");
  });

  it("rejects with a typed auth error and never asks for the session when the provider refuses", async () => {
    auth.signIn.mockResolvedValue({ data: null, error: { message: "Invalid email or password" } });

    const { result } = renderHook(() => useLogin(), { wrapper: Wrapper });
    let failure: unknown;
    await act(async () => {
      failure = await result.current.mutateAsync({ email: "michael@vinse.app", password: "nope" }).catch((e: unknown) => e);
    });

    expect(failure).toBeInstanceOf(AuthFlowError);
    expect((failure as AuthFlowError).reason).toBe("invalid_credentials");
    expect((failure as AuthFlowError).name).toBe("AuthFlowError");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(localStorage.getItem("sicurre_auth_provider")).toBeNull();
  });

  it.each([
    { label: "the account already exists", error: { message: "User already exists" }, reason: "email_taken" },
    { label: "the email is already registered", error: { message: "Email already in use" }, reason: "email_taken" },
    { label: "the record already exist", error: { statusText: "Already exist" }, reason: "email_taken" },
    { label: "the email is not verified by code", error: { code: "EMAIL_NOT_VERIFIED" }, reason: "email_unverified" },
    { label: "the email is not verified by message", error: { message: "Email not verified" }, reason: "email_unverified" },
    { label: "the email is malformed", error: { message: "Invalid email" }, reason: "invalid_email" },
    { label: "the password is too short", error: { message: "Password too short" }, reason: "weak_password" },
    { label: "the password is weak", error: { message: "Weak password" }, reason: "weak_password" },
    { label: "the password length is wrong", error: { message: "Password length invalid" }, reason: "weak_password" },
    { label: "the password is wrong", error: { message: "Invalid password" }, reason: "invalid_password" },
    { label: "the user is unknown", error: { message: "User not found" }, reason: "invalid_credentials" },
    { label: "a bot check is required", error: { code: "TURNSTILE_REQUIRED" }, reason: "bot_verification_required" },
    { label: "the bot check failed", error: { code: "TURNSTILE_FAILED" }, reason: "bot_verification_failed" },
    { label: "the browser could not fetch", error: { message: "Failed to fetch" }, reason: "service_unavailable" },
    { label: "the network is down", error: { statusText: "Network Error" }, reason: "service_unavailable" },
    { label: "nothing recognisable is said", error: { status: 500 }, reason: "invalid_credentials" },
  ])("maps a provider error saying $label to the reason $reason", async ({ error, reason }) => {
    auth.signIn.mockResolvedValue({ data: null, error });

    const { result } = renderHook(() => useLogin(), { wrapper: Wrapper });
    let failure: unknown;
    await act(async () => {
      failure = await result.current.mutateAsync({ email: "michael@vinse.app", password: "x" }).catch((e: unknown) => e);
    });

    expect((failure as AuthFlowError).reason).toBe(reason);
  });
});

describe("useSignup", () => {
  it("registers with the provider, returns to sign-in after verification and forwards the bot token", async () => {
    auth.signUp.mockResolvedValue({ data: { user: { id: "u-2" } }, error: null });

    const { result } = renderHook(() => useSignup(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        name: "Michael",
        email: "michael@vinse.app",
        password: "hunter2hunter2",
        turnstileToken: "cf-token",
      });
    });

    expect(auth.signUp).toHaveBeenCalledWith({
      name: "Michael",
      email: "michael@vinse.app",
      password: "hunter2hunter2",
      callbackURL: `${window.location.origin}/?verified=1`,
      fetchOptions: { headers: { "x-turnstile-token": "cf-token" } },
    });
  });

  it("sends no extra fetch options when there is no bot token", async () => {
    auth.signUp.mockResolvedValue({ data: { user: { id: "u-2" } }, error: null });

    const { result } = renderHook(() => useSignup(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.mutateAsync({ name: "Michael", email: "michael@vinse.app", password: "hunter2hunter2" });
    });

    expect(auth.signUp).toHaveBeenCalledWith(expect.objectContaining({ fetchOptions: undefined }));
  });

  it("reports a taken email as a typed auth error", async () => {
    auth.signUp.mockResolvedValue({ data: null, error: { code: "USER_ALREADY_EXISTS", message: "User already exists" } });

    const { result } = renderHook(() => useSignup(), { wrapper: Wrapper });
    let failure: unknown;
    await act(async () => {
      failure = await result.current.mutateAsync({ name: "M", email: "michael@vinse.app", password: "x" }).catch((e: unknown) => e);
    });

    expect(failure).toBeInstanceOf(AuthFlowError);
    expect((failure as AuthFlowError).reason).toBe("email_taken");
  });

  it("falls back to the signup failure reason when the provider error is opaque", async () => {
    auth.signUp.mockResolvedValue({ data: null, error: { status: 500 } });

    const { result } = renderHook(() => useSignup(), { wrapper: Wrapper });
    let failure: unknown;
    await act(async () => {
      failure = await result.current.mutateAsync({ name: "M", email: "michael@vinse.app", password: "x" }).catch((e: unknown) => e);
    });

    expect((failure as AuthFlowError).reason).toBe("signup_failed");
  });
});

describe("useLogout", () => {
  it("posts to the auth sidecar, then wipes tenant storage and the query cache", async () => {
    respondWith({ success: true });
    seedStoredSession({ displayName: "Michael", email: "michael@vinse.app", role: "owner" });
    localStorage.setItem("sicurre_theme", "dark");
    client.setQueryData(["auth-session"], session);

    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });
    let outcome: { success: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.mutateAsync();
    });

    expect(outcome).toEqual({ success: true });
    expect(request()).toEqual(expect.objectContaining({
      url: "/api/auth/sign-out",
      method: "POST",
      credentials: "include",
      body: "{}",
      contentType: "application/json",
    }));
    expect(localStorage.getItem("sicurre_user_email")).toBeNull();
    expect(localStorage.getItem("sicurre_theme")).toBe("dark");
    expect(client.getQueryData(["auth-session"])).toBeUndefined();
  });

  it("still wipes storage and cache when the sidecar refuses the sign-out", async () => {
    respondWith({ detail: "nope" }, 500);
    seedStoredSession({ email: "michael@vinse.app" });
    client.setQueryData(["auth-session"], session);

    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await expect(act(() => result.current.mutateAsync())).rejects.toThrow("Déconnexion impossible.");
    expect(localStorage.getItem("sicurre_user_email")).toBeNull();
    expect(client.getQueryData(["auth-session"])).toBeUndefined();
  });
});

describe("useUpdateProfile", () => {
  it("patches the profile, persists the returned session and refreshes the session query", async () => {
    seedStoredSession({ authProvider: "google" });
    respondWith({ ...session, display_name: "M. Adebayo" });
    const invalidate = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useUpdateProfile(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.mutateAsync({ display_name: "M. Adebayo" });
    });

    expect(request()).toEqual(expect.objectContaining({
      url: "/v1/auth/profile",
      method: "PATCH",
      body: JSON.stringify({ display_name: "M. Adebayo" }),
      credentials: "include",
    }));
    expect(localStorage.getItem("sicurre_user_name")).toBe("M. Adebayo");
    expect(localStorage.getItem("sicurre_auth_provider")).toBe("google");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["auth-session"] });
  });
});

describe("useChangePassword", () => {
  it("asks the provider to change the password and revoke the other sessions", async () => {
    auth.changePassword.mockResolvedValue({ data: { status: true }, error: null });

    const { result } = renderHook(() => useChangePassword(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.mutateAsync({ current_password: "old-pass-123", new_password: "new-pass-456" });
    });

    expect(auth.changePassword).toHaveBeenCalledWith({
      currentPassword: "old-pass-123",
      newPassword: "new-pass-456",
      revokeOtherSessions: true,
    });
  });

  it("surfaces the provider message when the change is refused", async () => {
    auth.changePassword.mockResolvedValue({ data: null, error: { message: "Invalid password" } });

    const { result } = renderHook(() => useChangePassword(), { wrapper: Wrapper });

    await expect(
      act(() => result.current.mutateAsync({ current_password: "wrong", new_password: "new-pass-456" })),
    ).rejects.toThrow("Invalid password");
  });

  it("uses a French fallback when the provider gives no message", async () => {
    auth.changePassword.mockResolvedValue({ data: null, error: {} });

    const { result } = renderHook(() => useChangePassword(), { wrapper: Wrapper });

    await expect(
      act(() => result.current.mutateAsync({ current_password: "wrong", new_password: "new-pass-456" })),
    ).rejects.toThrow("Impossible de modifier le mot de passe.");
  });
});
