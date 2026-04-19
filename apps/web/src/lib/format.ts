import { formatDistanceToNowStrict, parseISO } from "date-fns";

/**
 * Human-readable duration from a millisecond count.
 * 750 -> "750ms", 62_000 -> "1m 2s", 3_900_000 -> "1h 5m".
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remSeconds = seconds % 60;
  if (minutes < 60) return remSeconds ? `${minutes}m ${remSeconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return remMinutes ? `${hours}h ${remMinutes}m` : `${hours}h`;
}

/**
 * "3 minutes ago" / "in 2 hours" style relative string.
 */
export function formatRelative(input: string | Date | null | undefined): string {
  if (!input) return "—";
  try {
    const date = typeof input === "string" ? parseISO(input) : input;
    return `${formatDistanceToNowStrict(date, { addSuffix: true })}`;
  } catch {
    return "—";
  }
}

const numberFormatter = new Intl.NumberFormat("en-US");

export function formatNumber(value: number | null | undefined, digits?: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (digits !== undefined) {
    return value.toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }
  if (Number.isInteger(value)) return numberFormatter.format(value);
  return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let value = bytes;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
}
