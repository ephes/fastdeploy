import { Deployment, ServiceById, Step } from './typings';
import { isId as id, isOptionalDeleted, isOptionalWireDate as date, isRecord as record, isStepState, isWireDate, wireDateToDate } from './wireValues';

function invalid(): never {
  // Do not include wire values in diagnostics (service data may be private).
  throw new Error('Invalid REST snapshot');
}

/** Details of a sync that needs confirmation of its current deletion candidates. */
export interface SyncRefusal {
  message: string;
  wouldDelete: string[];
  total: number;
  confirmation: string;
}

export function syncRefusal(value: unknown): SyncRefusal | null {
  if (!record(value)) return null;
  const { message, would_delete: wouldDelete, total, confirmation } = value;
  if (typeof message !== 'string' || !message.trim() || (total !== 0 && !id(total)) ||
      !Array.isArray(wouldDelete) || wouldDelete.length > total ||
      typeof confirmation !== 'string' || confirmation.length !== 64 || !/^[0-9a-f]+$/.test(confirmation)) return null;
  const names = new Set<string>();
  for (const name of wouldDelete) {
    if (typeof name !== 'string' || !name.length || names.has(name)) return null;
    names.add(name);
  }
  return { message, wouldDelete: [...names], total, confirmation };
}

/** Only admit the fields used by the credential consumer; never echo wire values. */
export function serviceToken(value: unknown): string {
  if (!record(value) || value.token_type !== 'bearer' ||
      typeof value.service_token !== 'string' || value.service_token.length === 0 ||
      value.service_token.length > 16 * 1024 || !/^[\x21-\x7e]+$/.test(value.service_token)) return invalid();
  return value.service_token;
}

/** Admit the complete response and project fields before any live-store mutation. */
export function stepSnapshot(value: unknown, deploymentId: number): Step[] {
  if (!Array.isArray(value)) return invalid();
  const seen = new Set<number>();
  return value.map(row => {
    if (!record(row) || ('type' in row && row.type !== 'step') ||
        !id(row.id) || seen.has(row.id) || row.deployment_id !== deploymentId ||
        !id(row.deployment_id) || typeof row.name !== 'string' || typeof row.message !== 'string' ||
        !isStepState(row.state) || !date(row.started) || !date(row.finished) ||
        !isOptionalDeleted(row.deleted)) return invalid();
    seen.add(row.id);
    return {
      id: row.id, deploymentId: row.deployment_id, name: row.name,
      state: row.state, message: row.message,
      started: row.started === null ? null : wireDateToDate(row.started),
      finished: row.finished === null ? null : wireDateToDate(row.finished),
      ...(row.type === 'step' ? { type: 'step' as const } : {}),
      ...(typeof row.deleted === 'boolean' ? { deleted: row.deleted } : {}),
    };
  });
}

export function serviceSnapshot(value: unknown): ServiceById {
  if (!Array.isArray(value)) return invalid();
  const snapshot: ServiceById = {};
  for (const row of value) {
    if (!record(row) || ('type' in row && row.type !== 'service') ||
        !id(row.id) || Object.hasOwn(snapshot, row.id) ||
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

export function deploymentSnapshot(value: unknown, serviceId?: number): Deployment {
  if (!record(value) || ('type' in value && value.type !== 'deployment') ||
      !id(value.id) || !id(value.service_id) ||
      (serviceId !== undefined && value.service_id !== serviceId) ||
      typeof value.origin !== 'string' || typeof value.user !== 'string' ||
      !isWireDate(value.started) || !date(value.finished) || !isOptionalDeleted(value.deleted)) return invalid();
  return {
    id: value.id, serviceId: value.service_id, origin: value.origin, user: value.user,
    started: wireDateToDate(value.started), finished: value.finished === null ? null : wireDateToDate(value.finished),
    ...(value.type === 'deployment' ? { type: 'deployment' as const } : {}),
    ...(typeof value.deleted === 'boolean' ? { deleted: value.deleted } : {}),
  };
}

export function deploymentPage(value: unknown, serviceId?: number, beforeId: number | null = null): Deployment[] {
  if (!Array.isArray(value) || value.length > 50) return invalid();
  let upper = beforeId ?? Infinity;
  return value.map(row => {
    const deployment = deploymentSnapshot(row, serviceId);
    if (deployment.id >= upper || deployment.deleted) return invalid();
    upper = deployment.id;
    return deployment;
  });
}

/** Stable descending pages; a short page (including empty) completes traversal. */
export function stepPage(value: unknown, deploymentId: number, beforeId: number | null): Step[] {
  if (!Array.isArray(value) || value.length > 25) return invalid();
  const steps = stepSnapshot(value, deploymentId);
  let upper = beforeId ?? Infinity;
  for (const step of steps) {
    if (step.id >= upper || step.deleted) return invalid();
    upper = step.id;
  }
  return steps;
}
