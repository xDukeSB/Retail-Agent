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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const attemptAutoLogin = async () => {
      // Bypass authentication: immediately mock an admin user
      const mockUser = {
        id: "mock_admin_id",
        email: "admin@retailai.local",
        full_name: "Admin User",
        role: "admin",
      };
      
      setToken("mock_token");
      api.setToken("mock_token");
      setUser(mockUser);
      setIsLoading(false);
      
      if (pathname === "/login") {
        router.push("/");
      }
    };

    attemptAutoLogin();
  }, [pathname, router]);

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
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
