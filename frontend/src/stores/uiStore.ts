// UI store (Zustand) — theme mode, global period window, and sector filter.
// These drive the header PeriodSelector/SectorFilter shared across pages.
import { create } from "zustand";

export type ThemeMode = "light" | "dark";
export type PeriodKey = "today" | "week" | "twoweek" | "month";

interface UIState {
  mode: ThemeMode;
  period: PeriodKey;
  sector: string | null; // industry group filter
  collapsed: boolean; // sidebar collapsed
  setMode: (m: ThemeMode) => void;
  toggleMode: () => void;
  setPeriod: (p: PeriodKey) => void;
  setSector: (s: string | null) => void;
  setCollapsed: (c: boolean) => void;
}

const KEY = "srp.ui";

function load(): Partial<UIState> {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return {};
}

const saved = load();

function persist(state: UIState) {
  const { mode, period, sector, collapsed } = state;
  localStorage.setItem(KEY, JSON.stringify({ mode, period, sector, collapsed }));
}

export const useUIStore = create<UIState>((set, get) => ({
  mode: (saved.mode as ThemeMode) || "dark",
  period: (saved.period as PeriodKey) || "week",
  sector: (saved.sector as string | null) ?? null,
  collapsed: (saved.collapsed as boolean) ?? false,
  setMode: (mode) => {
    set({ mode });
    persist(get());
  },
  toggleMode: () => {
    set({ mode: get().mode === "light" ? "dark" : "light" });
    persist(get());
  },
  setPeriod: (period) => {
    set({ period });
    persist(get());
  },
  setSector: (sector) => {
    set({ sector });
    persist(get());
  },
  setCollapsed: (collapsed) => {
    set({ collapsed });
    persist(get());
  },
}));
