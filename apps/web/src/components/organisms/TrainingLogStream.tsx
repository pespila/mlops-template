import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useEventSource } from "@/lib/hooks/useEventSource";
import { cn } from "@/lib/cn";

export interface LogLine {
  ts: string;
  level: "debug" | "info" | "warn" | "error";
  message: string;
}

interface TrainingLogStreamProps {
  url: string;
  enabled?: boolean;
  eventName?: string;
  className?: string;
  maxLines?: number;
}

const LEVEL_CLASS: Record<LogLine["level"], string> = {
  debug: "text-fg3",
  info: "text-fg1",
  warn: "text-warning",
  error: "text-danger",
};

const CONNECTION_LABEL: Record<string, string> = {
  idle: "Idle",
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
  closed: "Closed",
};

export function TrainingLogStream({
  url,
  enabled = true,
  eventName = "log",
  className,
  maxLines = 2000,
}: TrainingLogStreamProps) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [filter, setFilter] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const events = useMemo(() => [eventName] as const, [eventName]);

  const { connectionState } = useEventSource<LogLine>({
    url,
    events,
    enabled,
    onEvent: (_name, data) => {
      setLines((prev) => {
        const next = prev.length >= maxLines ? prev.slice(prev.length - maxLines + 1) : prev;
        return [...next, data];
      });
    },
  });

  const filtered = useMemo(() => {
    if (!filter.trim()) return lines;
    const needle = filter.toLowerCase();
    return lines.filter(
      (l) => l.message.toLowerCase().includes(needle) || l.level.includes(needle),
    );
  }, [lines, filter]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [filtered.length]);

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-md border border-[color:var(--border)] bg-bg-soft",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-[color:var(--border)] bg-bg px-3 py-2">
        <div className="relative flex-1">
          <Search
            size={14}
            strokeWidth={2}
            className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-fg3"
          />
          <input
            value={filter}
            onChange={(ev) => setFilter(ev.target.value)}
            placeholder="Filter logs"
            className="w-full rounded border border-[color:var(--border)] bg-bg py-1 pl-7 pr-2 text-xs text-fg1 focus:border-primary focus:outline-none"
          />
        </div>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-fg2">
          <span
            aria-hidden="true"
            className={cn(
              "h-1.5 w-1.5 rounded-pill",
              connectionState === "live"
                ? "bg-success animate-pulse-teal"
                : connectionState === "connecting" || connectionState === "reconnecting"
                  ? "bg-warning"
                  : "bg-fg3",
            )}
          />
          {CONNECTION_LABEL[connectionState]}
        </span>
      </div>
      <div
        ref={scrollRef}
        className="h-80 overflow-y-auto overflow-x-hidden font-mono text-[12px] leading-relaxed"
      >
        {filtered.length === 0 ? (
          <p className="p-4 text-fg3">Waiting for log lines…</p>
        ) : (
          filtered.map((line, idx) => (
            <div
              key={`${line.ts}-${idx}`}
              className={cn(
                "flex gap-3 px-3 py-0.5 hover:bg-bg-muted",
                LEVEL_CLASS[line.level],
              )}
            >
              <span className="shrink-0 text-fg3">
                {new Date(line.ts).toLocaleTimeString()}
              </span>
              <span className="shrink-0 uppercase text-[10px] font-semibold tracking-[0.08em]">
                {line.level}
              </span>
              <span className="whitespace-pre-wrap break-words">{line.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
