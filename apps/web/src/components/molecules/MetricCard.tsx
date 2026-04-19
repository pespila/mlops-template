import { Line, LineChart, ResponsiveContainer } from "recharts";

import { Eyebrow } from "@/components/atoms/Eyebrow";
import { MetricDelta } from "@/components/atoms/MetricDelta";
import { cn } from "@/lib/cn";

interface MetricCardProps {
  eyebrow: string;
  value: string;
  delta?: number;
  invertDelta?: boolean;
  sparkline?: Array<{ step: number; value: number }>;
  className?: string;
  footer?: string;
}

export function MetricCard({
  eyebrow,
  value,
  delta,
  invertDelta,
  sparkline,
  className,
  footer,
}: MetricCardProps) {
  return (
    <div className={cn("glass-card animate-fade-in !p-6", className)}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <div className="mt-3 flex items-end justify-between gap-4">
        <span className="font-display text-[32px] font-bold leading-none tracking-tight text-fg1">
          {value}
        </span>
        {delta !== undefined ? <MetricDelta value={delta} invert={invertDelta} /> : null}
      </div>
      {sparkline && sparkline.length > 1 ? (
        <div className="mt-4 h-12">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkline}>
              <Line
                type="monotone"
                dataKey="value"
                stroke="var(--primary)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      {footer ? <p className="mt-3 text-xs text-fg3">{footer}</p> : null}
    </div>
  );
}
