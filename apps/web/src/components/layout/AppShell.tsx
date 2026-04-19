import { Outlet } from "react-router-dom";

import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="min-h-screen bg-bg text-fg1">
      <div className="flex">
        <Sidebar />
        <main className="flex-1 min-h-screen p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
