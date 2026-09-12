// Auth store — the login feature is disabled for this deployment. A single
// hardcoded admin identity is always active so every page/tool is reachable
// without a login flow. The store keeps a stable shape (token/user/setters) so
// the API client and layout don't need special-casing.
import { create } from "zustand";

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  display_name?: string | null;
}

// Hardcoded identity (no login required). Role "admin" unlocks all tools.
export const DEV_USER: AuthUser = { id: 1, username: "admin", role: "admin", display_name: "管理员" };
const DEV_TOKEN = "dev-admin";

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  setAuth: (token: string, user: AuthUser) => void;
  setUser: (user: AuthUser | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: DEV_TOKEN,
  user: DEV_USER,
  // Setters are retained for API compatibility but always resolve to the admin.
  setAuth: (token, user) => set({ token, user }),
  setUser: (user) => set({ user: user ?? DEV_USER }),
  clear: () => set({ token: DEV_TOKEN, user: DEV_USER }),
}));

export const getToken = () => useAuthStore.getState().token;
export const isAuthenticated = () => !!useAuthStore.getState().token;
export const isAdmin = () => useAuthStore.getState().user?.role === "admin";
