import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, clearToken, getToken, setToken } from "./api.js";

const AuthContext = createContext(null);

export const ROLES = {
  SUPER: "super_admin",
  CENTRE: "centre_admin",
  OFFICER: "monitoring_officer",
};
export const ROLE_LABELS = {
  super_admin: "Super Administrator",
  centre_admin: "Training Centre Administrator",
  monitoring_officer: "Monitoring Officer",
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  // On first load, check that a stored token is still valid.
  useEffect(() => {
    if (!getToken()) return;
    api.get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener("skillwatch:logout", onLogout);
    return () => window.removeEventListener("skillwatch:logout", onLogout);
  }, []);

  const login = useCallback(async (email, password) => {
    const form = new URLSearchParams({ username: email, password });
    const { data } = await api.post("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
    }),
    [user, loading, login, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
