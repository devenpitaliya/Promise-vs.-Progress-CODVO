import type { Priority, ReviewResult, Task, TaskCreate, TaskUpdate, TargetSystem } from '../../types/api';

export type Decision = 'approve' | 'reject' | 'later';

export interface DraftFields {
  assignee: string;
  description: string;
  target_date: string;
  priority: Priority;
  target_system: TargetSystem;
  repository: string;
  external_ref: string;
}

export interface ReviewRow {
  /** Stable React key. Existing tasks use their id; added rows use a negative number until saved. */
  key: number;
  /** Backend id once the commitment exists server-side. */
  taskId: number | null;
  original: DraftFields | null;
  draft: DraftFields;
  decision: Decision;
}

export interface ReviewApi {
  update: (id: number, payload: TaskUpdate) => Promise<Task>;
  create: (payload: TaskCreate) => Promise<Task>;
  review: (meetingId: number, approveIds: number[], rejectIds: number[], defaultRepository?: string) => Promise<ReviewResult>;
}

function toDraft(task: Task): DraftFields {
  return {
    assignee: task.assignee,
    description: task.description,
    target_date: task.target_date ?? '',
    priority: task.priority,
    target_system: task.target_system,
    repository: task.repository ?? '',
    external_ref: task.external_ref ?? '',
  };
}

export function rowFromTask(task: Task): ReviewRow {
  const draft = toDraft(task);
  return { key: task.id, taskId: task.id, original: draft, draft: { ...draft }, decision: 'approve' };
}

const nullable = (value: string) => (value.trim() ? value.trim() : null);

/** Only the fields the reviewer actually changed, in API shape. */
export function changedFields(row: ReviewRow): TaskUpdate {
  if (!row.original) return {};
  const changes: TaskUpdate = {};
  const { draft, original } = row;
  if (draft.assignee.trim() !== original.assignee) changes.assignee = draft.assignee.trim();
  if (draft.description.trim() !== original.description) changes.description = draft.description.trim();
  if (draft.target_date !== original.target_date) changes.target_date = nullable(draft.target_date);
  if (draft.priority !== original.priority) changes.priority = draft.priority;
  if (draft.target_system !== original.target_system) changes.target_system = draft.target_system;
  if (draft.repository.trim() !== original.repository) changes.repository = nullable(draft.repository);
  if (draft.external_ref.trim() !== original.external_ref) changes.external_ref = nullable(draft.external_ref);
  return changes;
}

export function validateRow(row: ReviewRow): string | null {
  if (row.decision === 'reject') return null;
  if (!row.draft.assignee.trim()) return 'Owner is required.';
  if (!row.draft.description.trim()) return 'Commitment text is required.';
  if (row.draft.repository.trim() && !/^[A-Za-z0-9_.-]+(\/[A-Za-z0-9_.-]+)?$/.test(row.draft.repository.trim())) {
    return 'Repository must look like "repo" or "owner/repo".';
  }
  return null;
}

/**
 * Persist the reviewer's edits and decisions.
 * `onRowSaved` reports newly created ids so a retry after a partial failure never duplicates rows.
 */
export async function submitReview(
  api: ReviewApi,
  meetingId: number,
  rows: ReviewRow[],
  defaultRepository: string,
  onRowSaved: (key: number, taskId: number) => void,
): Promise<ReviewResult> {
  const approveIds: number[] = [];
  const rejectIds: number[] = [];

  for (const row of rows) {
    let taskId = row.taskId;

    if (taskId === null) {
      if (row.decision === 'reject') continue; // an added row that is rejected never needs to exist
      const created = await api.create({
        meeting_id: meetingId,
        assignee: row.draft.assignee.trim(),
        description: row.draft.description.trim(),
        target_date: nullable(row.draft.target_date),
        priority: row.draft.priority,
        target_system: row.draft.target_system,
        repository: nullable(row.draft.repository),
        external_ref: nullable(row.draft.external_ref),
      });
      taskId = created.id;
      onRowSaved(row.key, taskId);
    } else if (row.decision !== 'reject') {
      const changes = changedFields(row);
      if (Object.keys(changes).length > 0) await api.update(taskId, changes);
    }

    if (row.decision === 'approve') approveIds.push(taskId);
    if (row.decision === 'reject') rejectIds.push(taskId);
  }

  if (approveIds.length === 0 && rejectIds.length === 0) {
    return { approved: [], rejected_ids: [], sync_failures: [] };
  }
  return api.review(meetingId, approveIds, rejectIds, defaultRepository.trim() || undefined);
}
