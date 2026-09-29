import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "./api";
import type { AuthUser } from "./types";

interface AuthContextValue {
  user: AuthUser | null;
  initializing: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (fullName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

interface LoginResponse {
  access_token: string;
  user: AuthUser;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function restoreSession() {
      if (!getToken()) {
        setInitializing(false);
        return;
      }
      try {
        const me = await api<AuthUser>("/api/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        setToken(null);
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const register = useCallback(async (fullName: string, email: string, password: string) => {
    const result = await api<LoginResponse>("/api/auth/register", {
      method: "POST",
      body: { full_name: fullName, email, password },
    });
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, initializing, login, register, logout }),
    [user, initializing, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function isStaffRole(role?: string | null): boolean {
  return role === "admin" || role === "agent" || role === "reviewer" || role === "manager";
}
