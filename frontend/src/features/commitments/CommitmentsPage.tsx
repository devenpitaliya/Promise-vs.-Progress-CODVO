import { useMemo, useState, type DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import clsx from 'clsx';
import { LayoutList, Search, Sparkles } from 'lucide-react';

import { commitmentsApi } from '../../api/endpoints';
import { useCommitments, useUpdateCommitment } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { PriorityBadge, SimulatedBadge, VerificationBadge } from '../../components/ui/Badges';
import { STATUS_LABEL } from '../../components/ui/badgeMeta';
import { Button } from '../../components/ui/Button';
import { inputClass } from '../../components/ui/Field';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../../components/ui/States';
import { errorMessage } from '../../lib/api';
import { formatDate, initials } from '../../lib/format';
import type { Task, TaskStatus } from '../../types/api';

const COLUMNS: TaskStatus[] = ['OPEN', 'IN_PROGRESS', 'IN_REVIEW', 'BLOCKED', 'DONE'];

function TaskCard({ task, onOpen, onDragStart }: { task: Task; onOpen: () => void; onDragStart: (e: DragEvent) => void }) {
  const unverifiedDone = task.status === 'DONE' && task.verification_status !== 'VERIFIED_DONE';
  return (
    <button
      type="button"
      draggable
      onDragStart={onDragStart}
      onClick={onOpen}
      className="w-full space-y-2 rounded-lg border border-line bg-white p-3 text-left shadow-sm hover:border-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
    >
      <p className="line-clamp-3 text-sm font-medium text-ink">{task.description}</p>
      <div className="flex flex-wrap gap-1">
        <PriorityBadge priority={task.priority} />
        {task.sync_status === 'SYNCED' ? <VerificationBadge status={task.verification_status} /> : null}
        {task.sync_status === 'FAILED' && (
          <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-800">Sync failed</span>
        )}
        {task.is_simulated && <SimulatedBadge />}
      </div>
      {unverifiedDone && <p className="text-xs font-medium text-amber-700">Marked done, not verified in GitHub</p>}
      <div className="flex items-center justify-between text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink text-[9px] font-bold text-white">{initials(task.assignee)}</span>
          <span className="max-w-[8rem] truncate">{task.assignee}</span>
        </span>
        {task.target_date && <span>{formatDate(task.target_date)}</span>}
      </div>
    </button>
  );
}

export function CommitmentsPage({ onOpenTask }: { onOpenTask: (id: number) => void }) {
  const { data: tasks, isLoading, error, refetch } = useCommitments();
  const update = useUpdateCommitment();
  const [query, setQuery] = useState('');
  const [owner, setOwner] = useState('all');
  const [dragOver, setDragOver] = useState<TaskStatus | null>(null);
  const semantic = useMutation({ mutationFn: commitmentsApi.search });

  const tracked = useMemo(() => (tasks ?? []).filter((t) => t.approval_status === 'APPROVED' && t.status !== 'CANCELLED'), [tasks]);
  const pendingReview = (tasks ?? []).filter((t) => t.approval_status === 'PENDING').length;
  const owners = useMemo(() => [...new Set(tracked.map((t) => t.assignee))].sort(), [tracked]);

  const visible = tracked.filter((t) => {
    if (owner !== 'all' && t.assignee !== owner) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return [t.description, t.assignee, t.repository, t.external_ref, t.meeting_title].some((v) => v?.toLowerCase().includes(q));
  });

  const onDrop = (status: TaskStatus) => (event: DragEvent) => {
    event.preventDefault();
    setDragOver(null);
    const id = Number(event.dataTransfer.getData('text/plain'));
    const task = tracked.find((t) => t.id === id);
    if (task && task.status !== status) update.mutate({ id, payload: { status } });
  };

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  return (
    <>
      <PageHeader
        title="Commitments"
        description="Approved commitments by reported status. Moving a card to Done records what the owner says; only GitHub can mark it verified."
      />

      {pendingReview > 0 && (
        <Alert tone="warning" className="mb-4">
          {pendingReview} extracted commitment(s) are waiting for review on the Meetings page and are not tracked yet.
        </Alert>
      )}
      {update.isError && (
        <Alert tone="error" className="mb-4">
          {errorMessage(update.error, 'Could not update the commitment.')}
        </Alert>
      )}

      {tracked.length === 0 ? (
        <EmptyState icon={<LayoutList size={20} aria-hidden="true" />} title="Nothing tracked yet">
          Approve commitments from a meeting to start tracking them here.
        </EmptyState>
      ) : (
        <>
          <div className="mb-4 flex flex-col gap-3 rounded-xl border border-line bg-white p-3 md:flex-row md:items-center">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-subtle" aria-hidden="true" />
              <input
                aria-label="Filter commitments"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter by text, owner, repository or reference"
                className={`${inputClass} h-9 pl-9`}
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={<Sparkles size={13} aria-hidden="true" />}
              disabled={query.trim().length < 3}
              loading={semantic.isPending}
              onClick={() => semantic.mutate(query.trim())}
              title="Find commitments with similar meaning, across all meetings"
            >
              Search by meaning
            </Button>
            <select aria-label="Filter by owner" value={owner} onChange={(e) => setOwner(e.target.value)} className={`${inputClass} h-9 md:w-56`}>
              <option value="all">All owners</option>
              {owners.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </div>

          {semantic.data && (
            <div className="mb-4 rounded-xl border border-line bg-white p-4">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-ink">Similar commitments</h2>
                <Button variant="ghost" size="sm" onClick={() => semantic.reset()}>
                  Close
                </Button>
              </div>
              {!semantic.data.available ? (
                <p className="text-sm text-muted">Semantic search is unavailable on this server.</p>
              ) : semantic.data.results.length === 0 ? (
                <p className="text-sm text-muted">No similar commitments found.</p>
              ) : (
                <ul className="space-y-1">
                  {semantic.data.results.map(({ task, score }) => (
                    <li key={task.id}>
                      <button type="button" onClick={() => onOpenTask(task.id)} className="w-full rounded px-2 py-1 text-left text-sm hover:bg-canvas">
                        <span className="font-medium text-ink">{task.assignee}</span> · {task.description}
                        <span className="ml-2 text-xs text-muted">{Math.round(score * 100)}% match</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {semantic.isError && (
            <Alert tone="error" className="mb-4">
              {errorMessage(semantic.error)}
            </Alert>
          )}

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {COLUMNS.map((status) => {
              const items = visible.filter((t) => t.status === status).sort((a, b) => a.priority - b.priority);
              return (
                <section
                  key={status}
                  aria-label={`${STATUS_LABEL[status]} (${items.length})`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(status);
                  }}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={onDrop(status)}
                  className={clsx(
                    'flex min-h-[16rem] flex-col rounded-xl border p-2.5',
                    dragOver === status ? 'border-brand bg-brand-soft' : 'border-line bg-canvas',
                  )}
                >
                  <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold text-ink">
                    {STATUS_LABEL[status]}
                    <span className="rounded-full bg-white px-2 text-xs text-muted">{items.length}</span>
                  </h2>
                  <div className="space-y-2">
                    {items.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        onOpen={() => onOpenTask(task.id)}
                        onDragStart={(e) => e.dataTransfer.setData('text/plain', String(task.id))}
                      />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
