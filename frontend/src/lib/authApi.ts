/**
 * Accounts.
 *
 * The session lives in an httpOnly cookie the browser sends automatically,
 * so there is no token to store, attach, or accidentally leak into a log.
 * `credentials: "include"` is what makes that work once the API is on a
 * different origin than the app.
 */

export interface User {
  id: string;
  name: string;
  email: string;
  createdAt: string;
  lastLoginAt: string | null;
}

interface RawUser {
  id: string;
  name: string;
  email: string;
  created_at: string;
  last_login_at: string | null;
}

const toUser = (raw: RawUser): User => ({
  id: raw.id,
  name: raw.name,
  email: raw.email,
  createdAt: raw.created_at,
  lastLoginAt: raw.last_login_at,
});

export interface ForgotPasswordResult {
  message: string;
  /** Whether mail actually left the server. False when none is configured. */
  sent: boolean;
  /**
   * The reset link, and only ever present on a local machine with no mail
   * server. It is how development finishes a reset at all; anywhere else
   * the server withholds it, because returning it would let anyone reset
   * anyone's password just by asking.
   */
  link: string | null;
}

const BASE = "/api/v1";

export class AuthError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      ...init,
    });
  } catch {
    throw new AuthError(
      "Cannot reach the server. Is the backend running?",
      0,
    );
  }

  if (!response.ok) {
    let detail = `Something went wrong (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // FastAPI validation errors arrive as a list. Show the first one in
        // plain words rather than the raw object.
        const first = body.detail[0] as { msg?: string } | undefined;
        if (first?.msg) detail = first.msg;
      }
    } catch {
      /* not json */
    }
    throw new AuthError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const authApi = {
  async signUp(name: string, email: string, password: string): Promise<User> {
    return toUser(
      await request<RawUser>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      }),
    );
  },

  async logIn(email: string, password: string): Promise<User> {
    return toUser(
      await request<RawUser>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    );
  },

  async logOut(): Promise<void> {
    await request<void>("/auth/logout", { method: "POST" });
  },

  /**
   * Ask for a reset link.
   *
   * Answers the same way whether or not the address has an account, so the
   * screen must never try to read "did this email exist" out of it.
   */
  async forgotPassword(email: string): Promise<ForgotPasswordResult> {
    return request<ForgotPasswordResult>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  /** Set a new password from a link, and sign in. */
  async resetPassword(token: string, password: string): Promise<User> {
    return toUser(
      await request<RawUser>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      }),
    );
  },

  /** The signed-in account, or null. Called once when the app loads. */
  async me(): Promise<User | null> {
    try {
      return toUser(await request<RawUser>("/auth/me"));
    } catch (err) {
      if (err instanceof AuthError && err.status === 401) return null;
      throw err;
    }
  },
};
