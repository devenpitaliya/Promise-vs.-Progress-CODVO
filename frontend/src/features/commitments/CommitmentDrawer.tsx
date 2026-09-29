import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, FlaskConical, Quote, RefreshCcw } from 'lucide-react';

import { commitmentsApi } from '../../api/endpoints';
import { useInvalidateTracking, useSystemStatus } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { ApprovalBadge, PriorityBadge, SimulatedBadge, VerificationBadge } from '../../components/ui/Badges';
import { PRIORITIES, PRIORITY_META, STATUS_LABEL } from '../../components/ui/badgeMeta';
import { Button } from '../../components/ui/Button';
import { SelectField, TextField } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { ErrorState, LoadingState } from '../../components/ui/States';
import { errorMessage } from '../../lib/api';
import { formatDate, formatDateTime } from '../../lib/format';
import type { Priority, Task, TaskStatus, TaskUpdate } from '../../types/api';

const STATUSES = Object.keys(STATUS_LABEL) as TaskStatus[];
type SimState = 'open' | 'merged' | 'closed' | 'closed_not_planned';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-3 py-2 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="col-span-2 text-ink">{children}</dd>
    </div>
  );
}

function EditForm({ task, onSaved, onCancel }: { task: Task; onSaved: (updated: Task) => void; onCancel: () => void }) {
  const invalidate = useInvalidateTracking();
  const client = useQueryClient();
  const [form, setForm] = useState({
    description: task.description,
    assignee: task.assignee,
    target_date: task.target_date ?? '',
    priority: task.priority,
    repository: task.repository ?? '',
    external_ref: task.external_ref ?? '',
  });
  const save = useMutation({
    mutationFn: (payload: TaskUpdate) => commitmentsApi.update(task.id, payload),
    onSuccess: async (updated) => {
      client.setQueryData(['commitment', task.id], updated);
      await invalidate();
      onSaved(updated);
    },
  });

  const linkChanged = form.repository !== (task.repository ?? '') || form.external_ref !== (task.external_ref ?? '');

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({
          description: form.description.trim(),
          assignee: form.assignee.trim(),
          target_date: form.target_date || null,
          priority: form.priority,
          repository: form.repository.trim() || null,
          external_ref: form.external_ref.trim() || null,
        });
      }}
    >
      <TextField label="Commitment" value={form.description} maxLength={500} required onChange={(e) => setForm({ ...form, description: e.target.value })} />
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Owner" value={form.assignee} maxLength={120} required onChange={(e) => setForm({ ...form, assignee: e.target.value })} />
        <SelectField
          label="Priority"
          value={form.priority}
          onChange={(e) => setForm({ ...form, priority: Number(e.target.value) as Priority })}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {PRIORITY_META[p].label} - {PRIORITY_META[p].description.split(': ')[1]}
            </option>
          ))}
        </SelectField>
        <TextField label="Target date" type="date" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} />
        <TextField label="Repository" placeholder="owner/repo" value={form.repository} onChange={(e) => setForm({ ...form, repository: e.target.value })} />
        <TextField label="Reference" placeholder="PR #12" value={form.external_ref} onChange={(e) => setForm({ ...form, external_ref: e.target.value })} />
      </div>
      {linkChanged && task.sync_status === 'SYNCED' && (
        <Alert tone="warning">Changing the repository or reference unlinks the current ticket. Sync again afterwards.</Alert>
      )}
      {save.isError && <Alert tone="error">{errorMessage(save.error)}</Alert>}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending}>
          Save changes
        </Button>
      </div>
    </form>
  );
}

export function CommitmentDrawer({ taskId, onClose }: { taskId: number | null; onClose: () => void }) {
  const client = useQueryClient();
  const invalidate = useInvalidateTracking();
  const { data: system } = useSystemStatus();
  const [editing, setEditing] = useState(false);
  // Two-way sync: what the last edit did in GitHub (closed, reopened, commented...).
  const [trackerNote, setTrackerNote] = useState<string | null>(null);
  const { data: task, isLoading, error, refetch } = useQuery({
    queryKey: ['commitment', taskId],
    queryFn: () => commitmentsApi.get(taskId as number),
    enabled: taskId !== null,
  });

  useEffect(() => {
    setEditing(false);
    setTrackerNote(null);
  }, [taskId]);

  const onUpdated = async (updated: Task) => {
    if (updated.tracker_update) setTrackerNote(updated.tracker_update);
    client.setQueryData(['commitment', updated.id], updated);
    await invalidate();
  };

  const setStatus = useMutation({ mutationFn: (status: TaskStatus) => commitmentsApi.update(taskId as number, { status }), onSuccess: onUpdated });
  const retrySync = useMutation({ mutationFn: () => commitmentsApi.retrySync(taskId as number), onSuccess: onUpdated });
  const simulate = useMutation({ mutationFn: (state: SimState) => commitmentsApi.simulate(taskId as number, state), onSuccess: onUpdated });
  const mutationError = setStatus.error || retrySync.error || simulate.error;

  const isJira = task?.target_system === 'jira';
  const tool = isJira ? 'Jira' : 'GitHub';
  const toolMode = isJira ? system?.jira_mode : system?.github_mode;
  const canSimulate = task?.is_simulated && task.sync_status === 'SYNCED' && toolMode === 'simulated';
  // Tracked in simulation before the tool was connected: offer to create/link the real ticket.
  const mirrors = task?.sync_status === 'SYNCED' && !task.is_simulated && toolMode === 'live';
  const needsLiveSync = task?.is_simulated && task.sync_status === 'SYNCED' && toolMode === 'live';
  const isPr = task?.target_system === 'github_pr';

  return (
    <Modal open={taskId !== null} onClose={onClose} variant="drawer" title={task ? task.description : 'Commitment'} description={task?.meeting_title ?? undefined}>
      {isLoading ? (
        <LoadingState />
      ) : error || !task ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : editing ? (
        <EditForm
          task={task}
          onCancel={() => setEditing(false)}
          onSaved={(updated) => {
            setEditing(false);
            if (updated.tracker_update) setTrackerNote(updated.tracker_update);
          }}
        />
      ) : (
        <div className="space-y-6">
          {mutationError && <Alert tone="error">{errorMessage(mutationError)}</Alert>}

          {task.source_quote && (
            <figure className="rounded-lg bg-canvas p-3">
              <figcaption className="mb-1 flex items-center gap-1 text-xs font-medium text-muted">
                <Quote size={12} aria-hidden="true" /> What was said
              </figcaption>
              <blockquote className="text-sm italic text-body">{task.source_quote}</blockquote>
            </figure>
          )}

          <section>
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink">Promise</h3>
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
            </div>
            <dl className="divide-y divide-line">
              <Row label="Owner">{task.assignee}</Row>
              <Row label="Priority">
                <PriorityBadge priority={task.priority} />
              </Row>
              <Row label="Target date">{formatDate(task.target_date)}</Row>
              <Row label="Review">
                <ApprovalBadge status={task.approval_status} />
              </Row>
              <Row label="Track as">
                {task.target_system === 'github_pr' ? 'GitHub pull request' : task.target_system === 'jira' ? 'Jira' : 'GitHub issue'}
                {task.repository && <span className="ml-1 font-mono text-xs text-muted">{task.repository}</span>}
                {task.external_ref && <span className="ml-1 font-mono text-xs text-muted">{task.external_ref}</span>}
              </Row>
            </dl>
          </section>

          {task.approval_status === 'APPROVED' && (
            <section>
              <h3 className="mb-1 text-sm font-semibold text-ink">Reported status</h3>
              {trackerNote && (
                <Alert tone={/not updated/i.test(trackerNote) ? 'warning' : 'info'} className="mb-2">
                  {trackerNote}
                </Alert>
              )}
              <SelectField
                label="Status as reported by the owner"
                value={task.status}
                disabled={setStatus.isPending}
                onChange={(e) => setStatus.mutate(e.target.value as TaskStatus)}
                hint={
                  mirrors
                    ? isPr
                      ? `Adds a comment to the PR in ${tool}. PRs are never closed or merged from here; merging in ${tool} verifies it.`
                      : `Also updates ${tool}: Done closes the issue, Cancelled closes it as not planned, reopening reopens it, and a comment records each change. A close from here counts as claimed until it is closed in ${tool}.`
                    : `This does not mark the commitment as verified; only ${tool} can.`
                }
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </SelectField>
            </section>
          )}

          {task.approval_status === 'APPROVED' && (
            <section>
              <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
                Progress in {tool} {task.is_simulated && <SimulatedBadge />}
              </h3>
              {task.sync_status === 'FAILED' ? (
                <Alert tone="error">
                  <p>{task.sync_error}</p>
                  <Button className="mt-2" size="sm" variant="secondary" loading={retrySync.isPending} onClick={() => retrySync.mutate()} icon={<RefreshCcw size={12} aria-hidden="true" />}>
                    Retry sync
                  </Button>
                </Alert>
              ) : task.sync_status === 'NOT_SYNCED' ? (
                <div className="space-y-2">
                  <p className="text-sm text-muted">Not linked to {tool} yet.</p>
                  <Button size="sm" variant="secondary" loading={retrySync.isPending} onClick={() => retrySync.mutate()}>
                    Sync now
                  </Button>
                </div>
              ) : (
                <dl className="divide-y divide-line">
                  {task.external_key && <Row label="Ticket">{task.external_key}</Row>}
                  <Row label="Verification">
                    <VerificationBadge status={task.verification_status} />
                  </Row>
                  {task.verification_note && <Row label="Details">{task.verification_note}</Row>}
                  <Row label="Last checked">{formatDateTime(task.last_checked_at, 'Not checked yet')}</Row>
                  {task.verified_at && <Row label="Verified at">{formatDateTime(task.verified_at)}</Row>}
                  {task.github_url && (
                    <Row label="Link">
                      <a href={task.github_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand hover:underline">
                        Open in {tool} <ExternalLink size={12} aria-hidden="true" />
                      </a>
                    </Row>
                  )}
                </dl>
              )}
            </section>
          )}

          {needsLiveSync && (
            <section className="rounded-lg border border-sky-200 bg-sky-50 p-4">
              <h3 className="text-sm font-semibold text-sky-900">Move to {tool}</h3>
              <p className="mb-3 mt-0.5 text-xs text-sky-900/80">
                This commitment was tracked in simulation before {tool} was connected. Syncing creates or links the real {isPr ? 'pull request' : 'ticket'}; from then on
                only {tool} decides whether it is done.
              </p>
              <Button size="sm" loading={retrySync.isPending} onClick={() => retrySync.mutate()} icon={<RefreshCcw size={12} aria-hidden="true" />}>
                Sync to {tool} now
              </Button>
            </section>
          )}

          {canSimulate && (
            <section className="rounded-lg border border-violet-200 bg-violet-50 p-4">
              <h3 className="flex items-center gap-1.5 text-sm font-semibold text-violet-900">
                <FlaskConical size={14} aria-hidden="true" /> Simulate a {tool} event
              </h3>
              <p className="mb-3 mt-0.5 text-xs text-violet-900/80">
                {tool} is not connected, so you can move this simulated {isPr ? 'pull request' : 'issue'} to test the closed loop.
              </p>
              <div className="flex flex-wrap gap-2">
                {isPr ? (
                  <>
                    <Button size="sm" variant="secondary" loading={simulate.isPending && simulate.variables === 'merged'} onClick={() => simulate.mutate('merged')}>
                      Merge PR
                    </Button>
                    <Button size="sm" variant="secondary" loading={simulate.isPending && simulate.variables === 'closed'} onClick={() => simulate.mutate('closed')}>
                      Close without merging
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" variant="secondary" loading={simulate.isPending && simulate.variables === 'closed'} onClick={() => simulate.mutate('closed')}>
                      Close as completed
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={simulate.isPending && simulate.variables === 'closed_not_planned'}
                      onClick={() => simulate.mutate('closed_not_planned')}
                    >
                      Close as not planned
                    </Button>
                  </>
                )}
                <Button size="sm" variant="ghost" loading={simulate.isPending && simulate.variables === 'open'} onClick={() => simulate.mutate('open')}>
                  Reopen
                </Button>
              </div>
            </section>
          )}
        </div>
      )}
    </Modal>
  );
}
