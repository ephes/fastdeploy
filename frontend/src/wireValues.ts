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
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value));
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
