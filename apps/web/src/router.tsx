import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { Dashboard } from "@/pages/Dashboard";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      // datasets, experiments, models, deployments, settings land in subsequent commits
    ],
  },
]);
