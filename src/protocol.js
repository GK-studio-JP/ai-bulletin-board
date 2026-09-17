export const TASK_STATUS = Object.freeze({
  OPEN: 'open',
  CLAIMED: 'claimed',
  WORKING: 'working',
  HANDOFF: 'handoff',
  BLOCKED: 'blocked',
  DONE: 'done',
  CANCELLED: 'cancelled',
});

const transitions = Object.freeze({
  open: new Set(['claimed', 'cancelled']),
  claimed: new Set(['working', 'handoff', 'blocked', 'open', 'cancelled']),
  working: new Set(['handoff', 'blocked', 'done', 'open', 'cancelled']),
  handoff: new Set(['claimed', 'open', 'cancelled']),
  blocked: new Set(['working', 'handoff', 'open', 'cancelled']),
  done: new Set([]),
  cancelled: new Set([]),
});

export function canTransition(from, to) {
  return transitions[from]?.has(to) ?? false;
}

export function leaseIsActive(task, now = new Date()) {
  if (!task?.claimed_by || !task?.lease_expires_at) return false;
  return new Date(task.lease_expires_at).getTime() > now.getTime();
}

export function isClaimable(task, agentId, now = new Date()) {
  if (!task || ['done', 'cancelled', 'blocked'].includes(task.status)) return false;
  if (!leaseIsActive(task, now)) return true;
  return task.claimed_by === agentId;
}

export function dependenciesSatisfied(task, tasksById) {
  return (task.depends_on ?? []).every((id) => tasksById.get(id)?.status === 'done');
}

export function capabilitiesSatisfied(task, agentCapabilities) {
  const available = new Set(agentCapabilities ?? []);
  return (task.capabilities ?? []).every((capability) => available.has(capability));
}

export function validateHandoff(payload) {
  const required = ['summary', 'result', 'artifacts', 'next_action'];
  const missing = required.filter((key) => payload?.[key] == null);
  return { ok: missing.length === 0, missing };
}
