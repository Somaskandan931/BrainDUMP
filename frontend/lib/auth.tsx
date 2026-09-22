"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { authApi, clearToken, onAuthCleared, setToken } from "@/services/api";
import { AuthUser } from "@/services/types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<AuthUser>;
  loginWithGoogle: (idToken: string) => Promise<void>;
  loginWithGithub: (code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  // Starts true: on first load we don't yet know if there's a valid
  // stored token, and RouteGuard needs to wait for that answer before
  // deciding whether to redirect to /login.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authApi
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));

    // A 401 from any request (not just an explicit logout click) clears
    // the token in services/api.ts and fires this event -- catch it here
    // so the UI drops back to signed-out state immediately.
    return onAuthCleared(() => setUser(null));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (email: string, password: string, name?: string): Promise<AuthUser> => {
    const res = await authApi.register({ email, password, name });
    if (res.user.is_verified === false) {
      // Registration creates an unverified account. Do not leave a usable
      // bearer token in localStorage while the user is waiting for email
      // confirmation; the backend also rejects unverified sessions.
      clearToken();
      setUser(null);
    } else {
      setToken(res.access_token);
      setUser(res.user);
    }
    return res.user;
  }, []);

  const loginWithGoogle = useCallback(async (idToken: string) => {
    const res = await authApi.loginWithGoogle(idToken);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const loginWithGithub = useCallback(async (code: string) => {
    const res = await authApi.loginWithGithub(code);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    // Revoke the refresh session server-side first (best-effort -- an
    // unreachable backend shouldn't strand the user signed in locally),
    // then clear the local access token regardless.
    try {
      await authApi.logout();
    } catch {
      // ignore -- clearToken() below still signs the user out locally
    }
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, loginWithGoogle, loginWithGithub, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}
