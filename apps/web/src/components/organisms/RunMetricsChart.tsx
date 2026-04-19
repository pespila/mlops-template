import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RunMetric } from "@/lib/api/client";

const SERIES_COLORS = [
  "var(--ai-teal-900)",
  "var(--ai-teal-700)",
  "var(--ai-teal-600)",
  "var(--ai-teal-400)",
  "var(--ai-teal-200)",
];

interface RunMetricsChartProps {
  metrics: RunMetric[];
  height?: number;
}

interface ChartRow {
  step: number;
  [metric: string]: number;
}

export function RunMetricsChart({ metrics, height = 280 }: RunMetricsChartProps) {
  const { data, series } = useMemo(() => {
    const byStep = new Map<number, ChartRow>();
    const names = new Set<string>();
    for (const m of metrics) {
      names.add(m.name);
      const row = byStep.get(m.step) ?? { step: m.step };
      row[m.name] = m.value;
      byStep.set(m.step, row);
    }
    return {
      data: Array.from(byStep.values()).sort((a, b) => a.step - b.step),
      series: Array.from(names),
    };
  }, [metrics]);

  if (data.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-[color:var(--border)] text-sm text-fg3">
        No metrics recorded yet.
      </div>
    );
  }

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="step"
            tick={{ fill: "var(--fg2)", fontSize: 12 }}
            stroke="var(--border)"
          />
          <YAxis
            tick={{ fill: "var(--fg2)", fontSize: 12 }}
            stroke="var(--border)"
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg)",
              borderRadius: 8,
              border: "1px solid var(--border-primary)",
              fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((name, idx) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={SERIES_COLORS[idx % SERIES_COLORS.length]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
