/**
 * Wire predicates shared by websocket and REST admission, so both paths keep
 * one contract for identifiers, timestamps, step states and deletion flags.
 */
export const STEP_STATES = ['pending', 'running', 'success', 'failure'] as const;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
export function isId(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
export function isWireDate(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  // Retain ISO offsets (extended/basic), fractional seconds and legacy naive
  // timestamps, but never let Date.parse roll an impossible day or 24:00 forward.
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:[Zz]|[+-](\d{2}):?(\d{2}))?$/.exec(value);
  if (!parts) return false;
  const [year, month, day, hour, minute, second, offsetHour, offsetMinute] = parts.slice(1).map(part => Number(part ?? 0));
  if (year === 0) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1] &&
    hour <= 23 && minute <= 59 && second <= 59 && offsetHour <= 23 && offsetMinute <= 59 &&
    Number.isFinite(wireDateToDate(value).getTime());
}
/** Convert an admitted timestamp, treating legacy values without an offset as UTC. */
export function wireDateToDate(value: string): Date {
  return new Date(/(?:[Zz]|[+-]\d{2}:?\d{2})$/.test(value) ? value : value + 'Z');
}

export function isOptionalWireDate(value: unknown): value is string | null {
  return value === null || isWireDate(value);
}
export function isStepState(value: unknown): value is (typeof STEP_STATES)[number] {
  return (STEP_STATES as readonly unknown[]).includes(value);
}
/** ``deleted`` is optional on the wire but must be a boolean when present. */
export function isOptionalDeleted(value: unknown): value is boolean | undefined {
  return value === undefined || typeof value === 'boolean';
}
