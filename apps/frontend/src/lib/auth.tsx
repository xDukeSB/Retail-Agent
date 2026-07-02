"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "./api";

interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (token: string) => void;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  login: () => {},
  logout: () => {},
  isLoading: true,
});

// Default admin credentials for auto-login (local-first, single-store mode)
const AUTO_LOGIN_EMAIL = "admin@retailai.local";
const AUTO_LOGIN_PASSWORD = "admin123";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const attemptAutoLogin = async () => {
      // 1. Try to reuse saved token from localStorage
      const saved = localStorage.getItem("retailai_token");
      if (saved) {
        api.setToken(saved);
        try {
          const me = await api.getMe();
          setToken(saved);
          setUser(me);
          setIsLoading(false);
          if (pathname === "/login") router.push("/");
          return;
        } catch {
          // Token expired or invalid — fall through to fresh login
          localStorage.removeItem("retailai_token");
          api.setToken(null);
        }
      }

      // 2. Auto-login with admin credentials (no user interaction needed)
      try {
        const result = await api.login(AUTO_LOGIN_EMAIL, AUTO_LOGIN_PASSWORD);
        const newToken = result.access_token;
        localStorage.setItem("retailai_token", newToken);
        api.setToken(newToken);
        const me = await api.getMe();
        setToken(newToken);
        setUser(me);
        if (pathname === "/login") router.push("/");
      } catch {
        // Backend not reachable yet — set placeholder so UI still renders
        setUser({
          id: "local",
          email: AUTO_LOGIN_EMAIL,
          full_name: "Admin User",
          role: "admin",
        });
      } finally {
        setIsLoading(false);
      }
    };

    attemptAutoLogin();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = (newToken: string) => {
    localStorage.setItem("retailai_token", newToken);
    setToken(newToken);
    api.setToken(newToken);
    api.getMe().then((u) => {
      setUser(u);
      router.push("/");
    });
  };

  const logout = () => {
    localStorage.removeItem("retailai_token");
    setToken(null);
    setUser(null);
    api.setToken(null);
    // Auto-login again immediately — no login page for local-first mode
    router.push("/");
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
