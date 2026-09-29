import { describe, expect, it, vi } from 'vitest';

import { changedFields, rowFromTask, submitReview, validateRow, type ReviewApi, type ReviewRow } from './reviewLogic';
import type { Task } from '../../types/api';

function task(id: number, overrides: Partial<Task> = {}): Task {
  return {
    id,
    meeting_id: 1,
    meeting_title: 'Standup',
    assignee: 'Maya Chen',
    description: `Task ${id}`,
    source_quote: null,
    target_date: '2026-09-30',
    priority: 2,
    speech_status: 'PROPOSED',
    target_system: 'github_issue',
    repository: null,
    external_ref: null,
    approval_status: 'PENDING',
    status: 'OPEN',
    sync_status: 'NOT_SYNCED',
    sync_error: null,
    is_simulated: false,
    github_url: null,
    github_issue_number: null,
    github_pr_number: null,
    external_key: null,
    verification_status: 'NOT_CHECKED',
    github_state: null,
    verification_note: null,
    last_checked_at: null,
    verified_at: null,
    created_at: '2026-09-27T10:00:00Z',
    updated_at: '2026-09-27T10:00:00Z',
    ...overrides,
  };
}

function mockApi(): ReviewApi & { [K in keyof ReviewApi]: ReturnType<typeof vi.fn> } {
  let nextId = 100;
  return {
    update: vi.fn(async (id: number) => task(id)),
    create: vi.fn(async () => task(nextId++)),
    review: vi.fn(async () => ({ approved: [], rejected_ids: [], sync_failures: [] })),
  };
}

describe('submitReview', () => {
  it('sends exactly the approved and rejected ids, never the ones left for later', async () => {
    const api = mockApi();
    const rows: ReviewRow[] = [
      { ...rowFromTask(task(1)), decision: 'approve' },
      { ...rowFromTask(task(2)), decision: 'reject' },
      { ...rowFromTask(task(3)), decision: 'later' },
    ];
    await submitReview(api, 1, rows, 'acme/api', () => {});
    expect(api.review).toHaveBeenCalledWith(1, [1], [2], 'acme/api');
    expect(api.update).not.toHaveBeenCalled();
  });

  it('sends a changed priority with the other edits', async () => {
    const api = mockApi();
    const row = rowFromTask(task(1));
    row.draft = { ...row.draft, priority: 1 };
    await submitReview(api, 1, [row], '', () => {});
    expect(api.update).toHaveBeenCalledWith(1, { priority: 1 });
  });

  it('saves edits before approving', async () => {
    const api = mockApi();
    const row = rowFromTask(task(1));
    row.draft = { ...row.draft, description: 'Merge the token fix', repository: 'acme/auth' };
    await submitReview(api, 1, [row], '', () => {});
    expect(api.update).toHaveBeenCalledWith(1, { description: 'Merge the token fix', repository: 'acme/auth' });
    expect(api.update.mock.invocationCallOrder[0]).toBeLessThan(api.review.mock.invocationCallOrder[0]);
    expect(api.review).toHaveBeenCalledWith(1, [1], [], undefined);
  });

  it('creates added commitments once, even when retried after a failure', async () => {
    const api = mockApi();
    api.review.mockRejectedValueOnce(new Error('network'));
    const added: ReviewRow = {
      key: -1,
      taskId: null,
      original: null,
      decision: 'approve',
      draft: { assignee: 'Sam', description: 'Write runbook', target_date: '', priority: 3, target_system: 'github_issue', repository: '', external_ref: '' },
    };
    let rows = [added];
    const onSaved = (key: number, taskId: number) => {
      rows = rows.map((r) => (r.key === key ? { ...r, taskId } : r));
    };

    await expect(submitReview(api, 1, rows, '', onSaved)).rejects.toThrow('network');
    await submitReview(api, 1, rows, '', onSaved);

    expect(api.create).toHaveBeenCalledTimes(1);
    expect(api.review).toHaveBeenLastCalledWith(1, [100], [], undefined);
  });

  it('skips creating rows that were added and then rejected', async () => {
    const api = mockApi();
    const added: ReviewRow = {
      key: -2,
      taskId: null,
      original: null,
      decision: 'reject',
      draft: { assignee: 'Sam', description: 'x', target_date: '', priority: 2, target_system: 'github_issue', repository: '', external_ref: '' },
    };
    const result = await submitReview(api, 1, [added], '', () => {});
    expect(api.create).not.toHaveBeenCalled();
    expect(api.review).not.toHaveBeenCalled();
    expect(result.approved).toEqual([]);
  });
});

describe('row helpers', () => {
  it('reports only changed fields, with blanks as null', () => {
    const row = rowFromTask(task(1, { repository: 'acme/api' }));
    row.draft = { ...row.draft, target_date: '', repository: 'acme/api' };
    expect(changedFields(row)).toEqual({ target_date: null });
  });

  it('validates owner, text and repository format', () => {
    const row = rowFromTask(task(1));
    expect(validateRow({ ...row, draft: { ...row.draft, assignee: ' ' } })).toMatch(/Owner/);
    expect(validateRow({ ...row, draft: { ...row.draft, repository: 'not a repo' } })).toMatch(/Repository/);
    expect(validateRow({ ...row, decision: 'reject', draft: { ...row.draft, description: '' } })).toBeNull();
  });
});
