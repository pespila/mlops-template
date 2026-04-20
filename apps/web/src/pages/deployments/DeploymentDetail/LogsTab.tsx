import { useQuery } from "@tanstack/react-query";

import { TrainingLogStream } from "@/components/organisms/TrainingLogStream";
import { api } from "@/lib/api/client";

interface LogsTabProps {
  deploymentId: string;
}

export function LogsTab({ deploymentId }: LogsTabProps) {
  const history = useQuery({
    queryKey: ["deployments", deploymentId, "logs"],
    queryFn: () => api.deployments.logs(deploymentId, 1000),
    enabled: Boolean(deploymentId),
    // Tail the container every couple of seconds; TrainingLogStream replaces
    // its state each time, so we don't accumulate duplicates.
    refetchInterval: 3000,
  });

  return (
    <TrainingLogStream
      url={`/sse/deployments/${deploymentId}/events`}
      eventName="log"
      enabled
      history={(history.data ?? []).map((l) => ({
        ts: l.ts,
        level: (l.level as "debug" | "info" | "warn" | "error") ?? "info",
        message: l.message,
      }))}
    />
  );
}
