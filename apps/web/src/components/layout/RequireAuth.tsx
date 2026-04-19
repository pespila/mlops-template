import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useCurrentUser } from "@/lib/hooks/useAuth";

interface RequireAuthProps {
  children: ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const { data, isPending, isError } = useCurrentUser();
  const location = useLocation();

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-fg3">
        <Loader2 size={18} strokeWidth={2} className="animate-spin" />
        <span className="text-sm">Checking your session</span>
      </div>
    );
  }

  if (isError || !data) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
