/**
 * Display helpers for times and durations. They accept anything a
 * store row may carry and return an empty string for unusable values.
 */

function time(value: unknown): number | null {
  if (!(value instanceof Date)) return null;
  const ms = value.getTime();
  return Number.isFinite(ms) ? ms : null;
}

/** "42 s", "1 min 35 s", "2 h 05 min" for a span between two dates. */
export function formatDuration(start: unknown, end: unknown): string {
  const from = time(start);
  const to = time(end);
  if (from === null || to === null || to < from) return "";
  const ms = to - from;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)} s`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${String(seconds % 60).padStart(2, "0")} s`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

/** "just now", "5 min ago", "3 h ago", "2 d ago", then the date. */
export function formatRelative(value: unknown, now: number): string {
  const then = time(value);
  if (then === null) return "";
  const seconds = Math.round((now - then) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  return new Date(then).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** Full local date and time, e.g. "27 Nov 2026, 09:51:19". */
export function formatDateTime(value: unknown): string {
  const then = time(value);
  if (then === null) return "";
  return new Date(then).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}
