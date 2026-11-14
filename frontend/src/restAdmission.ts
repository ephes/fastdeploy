import { ServiceById, Step } from './typings';
import { isId as id, isOptionalDeleted, isOptionalWireDate as date, isRecord as record, isStepState } from './wireValues';

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
        !isStepState(row.state) || !date(row.started) || !date(row.finished) ||
        !isOptionalDeleted(row.deleted)) return invalid();
    seen.add(row.id);
    return {
      id: row.id, deploymentId: row.deployment_id, name: row.name,
      state: row.state, message: row.message,
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
        typeof row.name !== 'string' || !record(row.data) || !isOptionalDeleted(row.deleted)) return invalid();
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
