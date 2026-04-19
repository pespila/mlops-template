import { TrainingLogStream } from "@/components/organisms/TrainingLogStream";

interface LogsTabProps {
  deploymentId: string;
}

export function LogsTab({ deploymentId }: LogsTabProps) {
  return (
    <TrainingLogStream url={`/sse/deployments/${deploymentId}/events`} eventName="log" enabled />
  );
}
