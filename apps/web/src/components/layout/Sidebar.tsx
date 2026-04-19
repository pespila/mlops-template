import { BarChart3, Boxes, Database, LayoutDashboard, Rocket, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { clsx } from "clsx";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/experiments", label: "Experiments", icon: BarChart3 },
  { to: "/models", label: "Models", icon: Boxes },
  { to: "/deployments", label: "Deployments", icon: Rocket },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="w-64 min-h-screen border-r border-border bg-bg-soft px-4 py-6">
      <div className="px-2 mb-8">
        <div className="flex items-center gap-2">
          <img src="/logo.svg" alt="" className="h-8 w-8" />
          <div>
            <div className="font-display font-extrabold text-lg tracking-tight text-fg1">
              AIpacken
            </div>
            <div className="font-subtext text-xs text-fg2 tracking-wide">AI Platform</div>
          </div>
        </div>
      </div>
      <nav className="flex flex-col gap-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary-soft text-primary"
                  : "text-fg2 hover:text-fg1 hover:bg-bg-muted",
              )
            }
          >
            <item.icon size={18} strokeWidth={2} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
