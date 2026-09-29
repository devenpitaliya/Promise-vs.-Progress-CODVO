import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { Plus, Quote } from 'lucide-react';

import { changedFields, rowFromTask, submitReview, validateRow, type Decision, type DraftFields, type ReviewRow } from './reviewLogic';
import { commitmentsApi } from '../../api/endpoints';
import { useInvalidateTracking, useSystemStatus } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { inputClass } from '../../components/ui/Field';
import { PRIORITIES, PRIORITY_META } from '../../components/ui/badgeMeta';
import { errorMessage } from '../../lib/api';
import { pluralize } from '../../lib/format';
import type { Meeting, Priority, ReviewResult, TargetSystem } from '../../types/api';

const DECISIONS: { value: Decision; label: string; active: string }[] = [
  { value: 'approve', label: 'Approve', active: 'bg-emerald-600 text-white' },
  { value: 'later', label: 'Later', active: 'bg-slate-600 text-white' },
  { value: 'reject', label: 'Reject', active: 'bg-rose-600 text-white' },
];

const SYSTEMS: { value: TargetSystem; label: string }[] = [
  { value: 'github_issue', label: 'GitHub issue' },
  { value: 'github_pr', label: 'GitHub PR' },
  { value: 'jira', label: 'Jira' },
];

interface Props {
  meeting: Meeting;
  onDone: (result: ReviewResult) => void;
  onCancel?: () => void;
}

let nextLocalKey = -1;

export function ReviewCommitments({ meeting, onDone, onCancel }: Props) {
  const invalidate = useInvalidateTracking();
  const { data: system } = useSystemStatus();
  const [rows, setRows] = useState<ReviewRow[]>(() =>
    meeting.tasks.filter((t) => t.approval_status === 'PENDING').map(rowFromTask),
  );
  const [defaultRepository, setDefaultRepository] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  const quotes = useMemo(() => new Map(meeting.tasks.map((t) => [t.id, t.source_quote])), [meeting.tasks]);
  const participantNames = meeting.participants.map((p) => p.name);
  const counts = {
    approve: rows.filter((r) => r.decision === 'approve').length,
    reject: rows.filter((r) => r.decision === 'reject').length,
    later: rows.filter((r) => r.decision === 'later').length,
  };
  const rowErrors = new Map(rows.map((r) => [r.key, validateRow(r)]));
  const hasErrors = [...rowErrors.values()].some(Boolean);
  const missingRepo =
    system?.github_mode === 'live' &&
    !defaultRepository.trim() &&
    rows.some((r) => r.decision === 'approve' && r.draft.target_system !== 'jira' && !r.draft.repository.trim());

  const patchRow = (key: number, patch: Partial<ReviewRow>) =>
    setRows((current) => current.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const patchDraft = (key: number, field: Exclude<keyof DraftFields, 'priority'>, value: string) =>
    setRows((current) => current.map((r) => (r.key === key ? { ...r, draft: { ...r.draft, [field]: value } } : r)));

  const addRow = () =>
    setRows((current) => [
      ...current,
      {
        key: nextLocalKey--,
        taskId: null,
        original: null,
        decision: 'approve',
        draft: {
          assignee: participantNames[0] ?? '',
          description: '',
          target_date: '',
          priority: 2,
          target_system: system?.default_tracker === 'jira' ? 'jira' : 'github_issue',
          repository: '',
          external_ref: '',
        },
      },
    ]);

  const setAll = (decision: Decision) => setRows((current) => current.map((r) => ({ ...r, decision })));

  const handleSubmit = async () => {
    setShowErrors(true);
    if (hasErrors) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitReview(commitmentsApi, meeting.id, rows, defaultRepository, (key, taskId) =>
        patchRow(key, { taskId }),
      );
      await invalidate();
      onDone(result);
    } catch (err) {
      setError(errorMessage(err, 'Saving the review failed. Your edits are kept; try again.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Nothing is sent to GitHub or Jira until you approve it. Edit anything the extraction got wrong.
        </p>
        <div className="flex gap-2 text-xs">
          <Button variant="ghost" size="sm" onClick={() => setAll('approve')}>
            Approve all
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setAll('later')}>
            Clear all
          </Button>
        </div>
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line-strong bg-white px-4 py-8 text-center text-sm text-muted">
          No commitments were found in this transcript. Add any that were missed.
        </div>
      ) : (
        <ul className="space-y-3">
          {rows.map((row, index) => {
            const rowError = showErrors ? rowErrors.get(row.key) : null;
            const quote = row.taskId !== null ? quotes.get(row.taskId) : null;
            const edited = row.original !== null && Object.keys(changedFields(row)).length > 0;
            const disabled = row.decision === 'reject';
            return (
              <li
                key={row.key}
                className={clsx(
                  'rounded-xl border bg-white p-4 transition-opacity',
                  rowError ? 'border-rose-300' : 'border-line',
                  disabled && 'opacity-60',
                )}
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-medium text-muted">
                    <span>#{index + 1}</span>
                    {row.taskId === null && <span className="rounded bg-brand-soft px-1.5 py-0.5 text-brand">Added by you</span>}
                    {edited && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-800">Edited</span>}
                  </div>
                  <div role="radiogroup" aria-label={`Decision for commitment ${index + 1}`} className="inline-flex rounded-lg border border-line p-0.5">
                    {DECISIONS.map((d) => (
                      <button
                        key={d.value}
                        type="button"
                        role="radio"
                        aria-checked={row.decision === d.value}
                        onClick={() => patchRow(row.key, { decision: d.value })}
                        className={clsx(
                          'h-7 rounded-md px-3 text-xs font-semibold',
                          row.decision === d.value ? d.active : 'text-muted hover:text-ink',
                        )}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>

                {quote && (
                  <p className="mb-3 flex gap-2 rounded-lg bg-canvas px-3 py-2 text-xs italic text-body">
                    <Quote size={12} className="mt-0.5 shrink-0 text-subtle" aria-hidden="true" />
                    {quote}
                  </p>
                )}

                <fieldset disabled={disabled} className="grid gap-3 sm:grid-cols-6">
                  <label className="sm:col-span-3">
                    <span className="mb-1 block text-xs font-medium text-muted">Commitment</span>
                    <input
                      className={`${inputClass} h-9`}
                      value={row.draft.description}
                      maxLength={500}
                      onChange={(e) => patchDraft(row.key, 'description', e.target.value)}
                      placeholder="What was promised"
                    />
                  </label>
                  <label className="sm:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-muted">Owner</span>
                    <input
                      className={`${inputClass} h-9`}
                      list={`owners-${meeting.id}`}
                      value={row.draft.assignee}
                      maxLength={120}
                      onChange={(e) => patchDraft(row.key, 'assignee', e.target.value)}
                    />
                  </label>
                  <label className="sm:col-span-1">
                    <span className="mb-1 block text-xs font-medium text-muted">Priority</span>
                    <select
                      className={`${inputClass} h-9 px-2`}
                      value={row.draft.priority}
                      onChange={(e) => patchRow(row.key, { draft: { ...row.draft, priority: Number(e.target.value) as Priority } })}
                    >
                      {PRIORITIES.map((p) => (
                        <option key={p} value={p}>
                          {PRIORITY_META[p].label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="sm:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-muted">Target date</span>
                    <input
                      type="date"
                      className={`${inputClass} h-9`}
                      value={row.draft.target_date}
                      onChange={(e) => patchDraft(row.key, 'target_date', e.target.value)}
                    />
                  </label>
                  <label className="sm:col-span-1">
                    <span className="mb-1 block text-xs font-medium text-muted">Track as</span>
                    <select
                      className={`${inputClass} h-9 px-2`}
                      value={row.draft.target_system}
                      onChange={(e) => patchDraft(row.key, 'target_system', e.target.value)}
                    >
                      {SYSTEMS.map((s) => {
                        const soon = s.value === 'jira' && !system?.integrations_available?.includes('jira');
                        return (
                          <option key={s.value} value={s.value} disabled={soon}>
                            {s.label}
                            {soon ? ' (coming soon)' : ''}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                  <label className="sm:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-muted">{row.draft.target_system === 'jira' ? 'Project key' : 'Repository'}</span>
                    <input
                      className={`${inputClass} h-9 font-mono text-xs`}
                      value={row.draft.repository}
                      maxLength={200}
                      placeholder={row.draft.target_system === 'jira' ? 'Default project' : 'owner/repo'}
                      onChange={(e) => patchDraft(row.key, 'repository', e.target.value)}
                    />
                  </label>
                  <label className="sm:col-span-1">
                    <span className="mb-1 block text-xs font-medium text-muted">Reference</span>
                    <input
                      className={`${inputClass} h-9 font-mono text-xs`}
                      value={row.draft.external_ref}
                      maxLength={100}
                      placeholder={row.draft.target_system === 'jira' ? 'PROJ-12' : 'PR #12'}
                      onChange={(e) => patchDraft(row.key, 'external_ref', e.target.value)}
                    />
                  </label>
                </fieldset>
                {rowError && <p className="mt-2 text-xs font-medium text-rose-700">{rowError}</p>}
              </li>
            );
          })}
        </ul>
      )}
      <datalist id={`owners-${meeting.id}`}>
        {participantNames.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>

      <Button variant="secondary" onClick={addRow} icon={<Plus size={14} aria-hidden="true" />}>
        Add a missed commitment
      </Button>

      <div className="rounded-xl border border-line bg-white p-4">
        <label className="block max-w-sm">
          <span className="mb-1 block text-sm font-medium text-ink">Default repository</span>
          <input
            className={`${inputClass} h-9 font-mono text-xs`}
            value={defaultRepository}
            placeholder="owner/repo"
            onChange={(e) => setDefaultRepository(e.target.value)}
          />
          <span className="mt-1 block text-xs text-muted">Used for approved commitments that have no repository.</span>
        </label>
        {missingRepo && (
          <Alert tone="warning" className="mt-3">
            Live GitHub is configured. Approved commitments without a repository will fail to sync until you set one.
          </Alert>
        )}
      </div>

      <div className="sticky bottom-0 -mx-1 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white/95 px-4 py-3 backdrop-blur">
        <p className="text-sm text-body" aria-live="polite">
          {counts.approve} to approve · {counts.reject} to reject · {pluralize(counts.later, 'commitment')} left for later
        </p>
        <div className="flex gap-2">
          {onCancel && (
            <Button variant="secondary" onClick={onCancel} disabled={submitting}>
              Cancel
            </Button>
          )}
          <Button onClick={handleSubmit} loading={submitting} disabled={counts.approve + counts.reject === 0}>
            {system?.github_mode === 'live' || system?.jira_mode === 'live' ? 'Save and create tickets' : 'Save decisions'}
          </Button>
        </div>
      </div>
    </div>
  );
}
