import { BarChart3, Boxes, Database, LayoutDashboard, Rocket, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { useT } from "@/i18n";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/state/uiStore";

const items = [
  { to: "/", key: "nav.dashboard", icon: LayoutDashboard, end: true },
  { to: "/datasets", key: "nav.datasets", icon: Database },
  { to: "/experiments", key: "nav.experiments", icon: BarChart3 },
  { to: "/models", key: "nav.models", icon: Boxes },
  { to: "/deployments", key: "nav.deployments", icon: Rocket },
  { to: "/settings", key: "nav.settings", icon: Settings },
];

export function Sidebar() {
  const t = useT();
  const collapsed = useUiStore((s) => s.sidebarCollapsed);

  return (
    <aside
      className={cn(
        "min-h-screen border-r border-border bg-bg-soft px-4 py-6 transition-[width]",
        collapsed ? "w-20" : "w-64",
      )}
    >
      <div className="mb-8 px-2">
        <div className="flex items-center gap-2">
          <img src="/logo.svg" alt="" className="h-8 w-8" />
          {!collapsed ? (
            <div>
              <div className="font-display text-lg font-extrabold tracking-tight text-fg1">
                AIpacken
              </div>
              <div className="font-subtext text-xs tracking-wide text-fg2">AI Platform</div>
            </div>
          ) : null}
        </div>
      </div>
      <nav className="flex flex-col gap-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary-soft text-primary"
                  : "text-fg2 hover:bg-bg-muted hover:text-fg1",
              )
            }
          >
            <item.icon size={18} strokeWidth={2} />
            {!collapsed ? <span>{t(item.key)}</span> : null}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
