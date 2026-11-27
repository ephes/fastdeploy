import { formatDateTime, formatDuration, formatRelative } from "../src/format";

const at = (ms: number) => new Date(Date.UTC(2026, 10, 27, 9, 0, 0) + ms);

describe("formatDuration", () => {
  it.each([
    [3_200, "3.2 s"],
    [41_000, "41 s"],
    [95_000, "1 min 35 s"],
    [128_000, "2 min 08 s"],
    [59_600, "1 min 00 s"],
    [3_900_000, "1 h 05 min"],
  ])("formats %i ms as %s", (ms, expected) => {
    expect(formatDuration(at(0), at(ms))).toBe(expected);
  });

  it("is empty for missing, invalid or reversed dates", () => {
    expect(formatDuration(null, at(0))).toBe("");
    expect(formatDuration(at(0), undefined)).toBe("");
    expect(formatDuration(new Date(NaN), at(0))).toBe("");
    expect(formatDuration(at(1000), at(0))).toBe("");
  });
});

describe("formatRelative", () => {
  const now = at(0).getTime();
  it.each([
    [10_000, "just now"],
    [5 * 60_000, "5 min ago"],
    [3 * 3_600_000, "3 h ago"],
    [2 * 86_400_000, "2 d ago"],
  ])("formats %i ms ago as %s", (ago, expected) => {
    expect(formatRelative(at(-ago), now)).toBe(expected);
  });

  it("falls back to the date after a week and treats clock skew as now", () => {
    expect(formatRelative(at(-30 * 86_400_000), now)).toContain("2026");
    expect(formatRelative(at(5_000), now)).toBe("just now");
  });

  it("is empty for unusable values", () => {
    expect(formatRelative(undefined, now)).toBe("");
    expect(formatRelative("2026-11-27", now)).toBe("");
    expect(formatDateTime(new Date(NaN))).toBe("");
  });
});
