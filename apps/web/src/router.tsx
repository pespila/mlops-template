import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Dashboard } from "@/pages/Dashboard";

const Login = lazy(() =>
  import("@/pages/login/Login").then((m) => ({ default: m.Login })),
);
const DatasetsList = lazy(() =>
  import("@/pages/datasets/DatasetsList").then((m) => ({ default: m.DatasetsList })),
);
const DatasetDetail = lazy(() =>
  import("@/pages/datasets/DatasetDetail").then((m) => ({ default: m.DatasetDetail })),
);
const ExperimentsList = lazy(() =>
  import("@/pages/experiments/ExperimentsList").then((m) => ({ default: m.ExperimentsList })),
);
const ExperimentDetail = lazy(() =>
  import("@/pages/experiments/ExperimentDetail").then((m) => ({ default: m.ExperimentDetail })),
);
const NewRunWizard = lazy(() =>
  import("@/pages/experiments/NewRunWizard").then((m) => ({ default: m.NewRunWizard })),
);
const RunDetail = lazy(() =>
  import("@/pages/experiments/RunDetail").then((m) => ({ default: m.RunDetail })),
);
const ModelsList = lazy(() =>
  import("@/pages/models/ModelsList").then((m) => ({ default: m.ModelsList })),
);
const ModelDetail = lazy(() =>
  import("@/pages/models/ModelDetail").then((m) => ({ default: m.ModelDetail })),
);
const DeploymentsList = lazy(() =>
  import("@/pages/deployments/DeploymentsList").then((m) => ({ default: m.DeploymentsList })),
);
const DeploymentDetail = lazy(() =>
  import("@/pages/deployments/DeploymentDetail").then((m) => ({ default: m.DeploymentDetail })),
);
const Settings = lazy(() =>
  import("@/pages/settings/Settings").then((m) => ({ default: m.Settings })),
);

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: "datasets", element: <DatasetsList /> },
      { path: "datasets/:id", element: <DatasetDetail /> },
      { path: "experiments", element: <ExperimentsList /> },
      { path: "experiments/new", element: <NewRunWizard /> },
      { path: "experiments/runs/:id", element: <RunDetail /> },
      { path: "experiments/:id", element: <ExperimentDetail /> },
      { path: "models", element: <ModelsList /> },
      { path: "models/:id", element: <ModelDetail /> },
      { path: "deployments", element: <DeploymentsList /> },
      { path: "deployments/:id", element: <DeploymentDetail /> },
      { path: "settings", element: <Settings /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
