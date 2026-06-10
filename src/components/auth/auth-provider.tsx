"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi, clearStoredAuthToken, getStoredAuthToken, setStoredAuthToken } from "@/lib/api";

export type AuthUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  family_member_id: string | null;
  family_member_name: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_login_at: string | null;
};

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  token: string | null;
  user: AuthUser | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  isLoading: boolean;
  setSession: (token: string, user: AuthUser) => void;
  clearSession: () => void;
  refreshSession: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setToken(getStoredAuthToken());
    setHydrated(true);
  }, []);

  const meQuery = useQuery({
    queryKey: ["auth", "me", token],
    queryFn: () => authApi.me().then((response) => response.data as AuthUser),
    enabled: hydrated && !!token && !user,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (meQuery.data) {
      setUser(meQuery.data);
    }
  }, [meQuery.data]);

  useEffect(() => {
    if (meQuery.isError && token) {
      clearSession();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meQuery.isError, token]);

  const clearSession = () => {
    clearStoredAuthToken();
    setToken(null);
    setUser(null);
    queryClient.clear();
  };

  const setSession = (nextToken: string, nextUser: AuthUser) => {
    setStoredAuthToken(nextToken);
    setToken(nextToken);
    setUser(nextUser);
    queryClient.setQueryData(["auth", "me", nextToken], nextUser);
  };

  const refreshSession = async () => {
    if (!token) {
      return;
    }
    const response = await authApi.me();
    setUser(response.data as AuthUser);
  };

  const status: AuthStatus = useMemo(() => {
    if (!hydrated || (token && meQuery.isLoading && !user)) {
      return "loading";
    }
    if (token && user) {
      return "authenticated";
    }
    return "unauthenticated";
  }, [hydrated, meQuery.isLoading, token, user]);

  const value: AuthContextValue = {
    token,
    user,
    status,
    isAuthenticated: status === "authenticated",
    isLoading: status === "loading",
    setSession,
    clearSession,
    refreshSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
