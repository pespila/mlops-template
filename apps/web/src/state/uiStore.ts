import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type Language = "en" | "de";

export interface UiState {
  sidebarCollapsed: boolean;
  language: Language;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setLanguage: (lang: Language) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      language: "en",
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setLanguage: (language) => set({ language }),
    }),
    {
      name: "aipacken.ui",
      version: 1,
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
