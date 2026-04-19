import { LogOut, PanelLeft } from "lucide-react";
import { Suspense } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { GlassCard } from "@/components/molecules/GlassCard";
import { useCurrentUser, useLogoutMutation } from "@/lib/hooks/useAuth";
import { useUiStore } from "@/state/uiStore";

import { Sidebar } from "./Sidebar";

function TopBar() {
  const { data: user } = useCurrentUser();
  const toggle = useUiStore((s) => s.toggleSidebar);
  const logout = useLogoutMutation();
  const navigate = useNavigate();

  return (
    <header className="flex items-center justify-between border-b border-border bg-bg px-6 py-3">
      <button
        type="button"
        onClick={toggle}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md text-fg2 hover:bg-bg-muted hover:text-fg1"
        aria-label="Toggle sidebar"
      >
        <PanelLeft size={18} strokeWidth={2} />
      </button>
      <div className="flex items-center gap-3 text-sm text-fg2">
        {user ? <span className="font-medium text-fg1">{user.email}</span> : null}
        {user ? (
          <button
            type="button"
            onClick={async () => {
              await logout.mutateAsync();
              navigate("/login");
            }}
            className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold text-fg2 hover:bg-bg-muted hover:text-fg1"
          >
            <LogOut size={14} strokeWidth={2} />
            Sign out
          </button>
        ) : null}
      </div>
    </header>
  );
}

function PageFallback() {
  return (
    <div className="max-w-3xl animate-fade-in">
      <GlassCard>
        <div className="h-8 w-48 animate-pulse rounded bg-bg-muted" />
        <div className="mt-4 h-4 w-full animate-pulse rounded bg-bg-muted" />
        <div className="mt-2 h-4 w-5/6 animate-pulse rounded bg-bg-muted" />
        <div className="mt-2 h-4 w-2/3 animate-pulse rounded bg-bg-muted" />
      </GlassCard>
    </div>
  );
}

export function AppShell() {
  return (
    <div className="min-h-screen bg-bg text-fg1">
      <div className="flex">
        <Sidebar />
        <div className="flex min-h-screen flex-1 flex-col">
          <TopBar />
          <main className="flex-1 p-8">
            <Suspense fallback={<PageFallback />}>
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>
    </div>
  );
}
