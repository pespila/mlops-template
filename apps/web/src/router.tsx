import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, useRouteError } from "react-router-dom";

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

function PageSuspense({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center text-sm text-fg3">Loading…</div>
      }
    >
      {children}
    </Suspense>
  );
}

function NotFound() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
      <p className="text-2xl font-bold text-fg1">404</p>
      <p className="text-sm text-fg2">Page not found.</p>
      <a href="/" className="text-sm text-primary hover:underline">
        Go home
      </a>
    </div>
  );
}

function RouteErrorBoundary() {
  const error = useRouteError();
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Something went wrong.";
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
      <p className="text-lg font-bold text-danger">Error</p>
      <p className="max-w-md text-sm text-fg2">{message}</p>
      <a href="/" className="text-sm text-primary hover:underline">
        Go home
      </a>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <PageSuspense>
        <Login />
      </PageSuspense>
    ),
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <Dashboard /> },
      {
        path: "datasets",
        element: (
          <PageSuspense>
            <DatasetsList />
          </PageSuspense>
        ),
      },
      {
        path: "datasets/:id",
        element: (
          <PageSuspense>
            <DatasetDetail />
          </PageSuspense>
        ),
      },
      {
        path: "experiments",
        element: (
          <PageSuspense>
            <ExperimentsList />
          </PageSuspense>
        ),
      },
      // "experiments/new" must come before "experiments/:id" — react-router
      // matches routes in definition order; putting /new after /:id would
      // treat the literal string "new" as an experiment ID.
      {
        path: "experiments/new",
        element: (
          <PageSuspense>
            <NewRunWizard />
          </PageSuspense>
        ),
      },
      {
        path: "experiments/runs/:id",
        element: (
          <PageSuspense>
            <RunDetail />
          </PageSuspense>
        ),
      },
      {
        path: "experiments/:id",
        element: (
          <PageSuspense>
            <ExperimentDetail />
          </PageSuspense>
        ),
      },
      {
        path: "models",
        element: (
          <PageSuspense>
            <ModelsList />
          </PageSuspense>
        ),
      },
      {
        path: "models/:id",
        element: (
          <PageSuspense>
            <ModelDetail />
          </PageSuspense>
        ),
      },
      {
        path: "deployments",
        element: (
          <PageSuspense>
            <DeploymentsList />
          </PageSuspense>
        ),
      },
      {
        path: "deployments/:id",
        element: (
          <PageSuspense>
            <DeploymentDetail />
          </PageSuspense>
        ),
      },
      {
        path: "settings",
        element: (
          <PageSuspense>
            <Settings />
          </PageSuspense>
        ),
      },
      { path: "404", element: <NotFound /> },
      { path: "*", element: <Navigate to="/404" replace /> },
    ],
  },
]);
