import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface SHAPFeatureImportance {
  feature: string;
  importance: number;
}

interface SHAPGlobalBarsProps {
  data: SHAPFeatureImportance[];
  height?: number;
}

export function SHAPGlobalBars({ data, height = 280 }: SHAPGlobalBarsProps) {
  const sorted = [...data].sort((a, b) => b.importance - a.importance).slice(0, 20);
  if (sorted.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-[color:var(--border)] text-sm text-fg3">
        No feature importances available.
      </div>
    );
  }

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={sorted} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
          <XAxis
            type="number"
            tick={{ fill: "var(--fg2)", fontSize: 12 }}
            stroke="var(--border)"
          />
          <YAxis
            type="category"
            dataKey="feature"
            tick={{ fill: "var(--fg2)", fontSize: 12 }}
            width={120}
            stroke="var(--border)"
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg)",
              borderRadius: 8,
              border: "1px solid var(--border-primary)",
              fontSize: 12,
            }}
          />
          <Bar dataKey="importance" fill="var(--ai-teal-700)" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
