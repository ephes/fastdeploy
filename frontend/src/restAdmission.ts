import { ServiceById, Step } from './typings';

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function id(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
function date(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value)));
}
function invalid(): never {
  // Do not include wire values in diagnostics (service data may be private).
  throw new Error('Invalid REST snapshot');
}

/** Admit the complete response and project fields before any live-store mutation. */
export function stepSnapshot(value: unknown, deploymentId: number): Step[] {
  if (!Array.isArray(value)) return invalid();
  const seen = new Set<number>();
  return value.map(row => {
    if (!record(row) || !id(row.id) || seen.has(row.id) || row.deployment_id !== deploymentId ||
        !id(row.deployment_id) || typeof row.name !== 'string' || typeof row.message !== 'string' ||
        !['pending', 'running', 'success', 'failure'].includes(row.state as string) ||
        !date(row.started) || !date(row.finished)) return invalid();
    seen.add(row.id);
    return {
      id: row.id, deploymentId: row.deployment_id, name: row.name,
      state: row.state as Step['state'], message: row.message,
      started: row.started === null ? null : new Date(row.started),
      finished: row.finished === null ? null : new Date(row.finished),
      ...(row.type === 'step' ? { type: 'step' as const } : {}),
      ...(typeof row.deleted === 'boolean' ? { deleted: row.deleted } : {}),
    };
  });
}

export function serviceSnapshot(value: unknown): ServiceById {
  if (!Array.isArray(value)) return invalid();
  const snapshot: ServiceById = {};
  for (const row of value) {
    if (!record(row) || !id(row.id) || Object.hasOwn(snapshot, row.id) ||
        typeof row.name !== 'string' || !record(row.data)) return invalid();
    snapshot[row.id] = {
      id: row.id, name: row.name, data: row.data,
      ...(row.type === 'service' ? { type: 'service' as const } : {}),
      ...(typeof row.deleted === 'boolean' ? { deleted: row.deleted } : {}),
    };
  }
  return snapshot;
}

export function serviceNamesSnapshot(value: unknown): string[] {
  if (!Array.isArray(value) || value.some(name => typeof name !== 'string') ||
      new Set(value).size !== value.length) return invalid();
  return [...value];
}
