import { useState } from 'react';
import clsx from 'clsx';
import { useMutation } from '@tanstack/react-query';
import { BellRing, CalendarClock, Mail, RefreshCcw } from 'lucide-react';

import { BriefingModal } from './BriefingModal';
import { RetryFailedModal } from '../commitments/RetryFailedModal';
import { ScheduleModal } from './ScheduleModal';
import { commitmentsApi, reconciliationApi } from '../../api/endpoints';
import { useInvalidateTracking, useMeetings, useReport, useRunReconciliation, useSystemStatus } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { PriorityBadge, SimulatedBadge, VerdictBadge } from '../../components/ui/Badges';
import { Button } from '../../components/ui/Button';
import { inputClass } from '../../components/ui/Field';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../../components/ui/States';
import { errorMessage } from '../../lib/api';
import { formatDate, formatDateTime } from '../../lib/format';
import type { ReconciliationItem, Verdict } from '../../types/api';

type Filter = 'attention' | 'claimed' | 'verified' | 'all';

const FILTERS: { id: Filter; label: string; verdicts: Verdict[] | null }[] = [
  { id: 'attention', label: 'Needs attention', verdicts: ['OVERDUE', 'DUE_TODAY', 'BLOCKED', 'AT_RISK'] },
  { id: 'claimed', label: 'Claimed, unverified', verdicts: ['CLAIMED_UNVERIFIED'] },
  { id: 'verified', label: 'Verified done', verdicts: ['VERIFIED_DONE'] },
  { id: 'all', label: 'All', verdicts: null },
];

const RISK_BAR: Record<ReconciliationItem['risk_level'], string> = {
  LOW: 'bg-emerald-500',
  MEDIUM: 'bg-amber-400',
  HIGH: 'bg-orange-500',
  CRITICAL: 'bg-rose-600',
};

function timing(item: ReconciliationItem): string {
  if (!item.target_date) return 'No target date';
  if (item.days_overdue) return `${formatDate(item.target_date)} · ${item.days_overdue}d overdue`;
  if (item.days_remaining === 0) return `${formatDate(item.target_date)} · today`;
  return `${formatDate(item.target_date)} · in ${item.days_remaining}d`;
}

export function ReconciliationPage({ onOpenTask }: { onOpenTask: (id: number) => void }) {
  const [meetingId, setMeetingId] = useState<number | undefined>(undefined);
  const [filter, setFilter] = useState<Filter>('attention');
  const [modal, setModal] = useState<'briefing' | 'schedule' | 'retry' | null>(null);
  const { data: meetings = [] } = useMeetings();
  const { data: report, isLoading, error, refetch } = useReport(meetingId);
  const run = useRunReconciliation();
  const { data: system } = useSystemStatus();
  const remind = useMutation({ mutationFn: () => reconciliationApi.remindOnSlack(meetingId) });
  const invalidate = useInvalidateTracking();
  const moveToLive = useMutation({ mutationFn: commitmentsApi.syncSimulated, onSuccess: () => invalidate() });
  // Items tracked in simulation whose tool (GitHub or Jira) has since been connected.
  const failedSyncs = (report?.items ?? []).filter((i) => i.sync_status === 'FAILED').length;
  const strandedSimulated = (report?.items ?? []).filter(
    (i) => i.is_simulated && (i.target_system === 'jira' ? system?.jira_mode : system?.github_mode) === 'live',
  ).length;

  const scopeLabel = meetingId ? meetings.find((m) => m.id === meetingId)?.title ?? 'Selected meeting' : 'All meetings';
  const lastChecked = report?.items.reduce<string | null>((latest, i) => (i.last_checked_at && (!latest || i.last_checked_at > latest) ? i.last_checked_at : latest), null);

  const counts = report?.counts;
  const attention = counts ? counts.OVERDUE + counts.DUE_TODAY + counts.BLOCKED + counts.AT_RISK : 0;
  const active = FILTERS.find((f) => f.id === filter)!;
  const items = (report?.items ?? []).filter((i) => !active.verdicts || active.verdicts.includes(i.verdict));

  return (
    <>
      <PageHeader
        title="Reconciliation"
        description="What was promised versus what GitHub and Jira show was delivered. Use it to open the next meeting."
        actions={
          <>
            <Button variant="secondary" onClick={() => setModal('schedule')} icon={<CalendarClock size={15} aria-hidden="true" />}>
              Schedules
            </Button>
            <Button variant="secondary" onClick={() => setModal('briefing')} icon={<Mail size={15} aria-hidden="true" />}>
              Briefing
            </Button>
            {system?.slack_connected && (
              <Button variant="secondary" onClick={() => remind.mutate()} loading={remind.isPending} icon={<BellRing size={15} aria-hidden="true" />}>
                Remind on Slack
              </Button>
            )}
            <Button onClick={() => run.mutate(meetingId)} loading={run.isPending} icon={<RefreshCcw size={15} aria-hidden="true" />}>
              Check trackers now
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          aria-label="Meeting scope"
          value={meetingId ?? ''}
          onChange={(e) => setMeetingId(e.target.value ? Number(e.target.value) : undefined)}
          className={`${inputClass} h-9 sm:max-w-xs`}
        >
          <option value="">All meetings</option>
          {meetings.map((m) => (
            <option key={m.id} value={m.id}>
              {m.title} ({formatDate(m.meeting_date)})
            </option>
          ))}
        </select>
        <span className="text-xs text-muted">
          Last checked: {formatDateTime(lastChecked, 'never')}
          {report && ` · "today" is ${formatDate(report.today)} (${report.timezone})`}
        </span>
      </div>

      {failedSyncs > 0 && (
        <Alert tone="warning" className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              {failedSyncs} commitment{failedSyncs === 1 ? '' : 's'} could not be created or linked in GitHub or Jira, so {failedSyncs === 1 ? 'it is' : 'they are'} not verified yet.
            </span>
            <Button size="sm" variant="secondary" onClick={() => setModal('retry')}>
              Fix and retry
            </Button>
          </div>
        </Alert>
      )}
      {strandedSimulated > 0 && (
        <Alert tone="info" className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              {strandedSimulated} commitment{strandedSimulated === 1 ? ' was' : 's were'} tracked in simulation before GitHub or Jira was connected. Sync them to create
              or link the real tickets.
            </span>
            <Button size="sm" onClick={() => moveToLive.mutate()} loading={moveToLive.isPending}>
              Sync to connected tools
            </Button>
          </div>
        </Alert>
      )}
      {moveToLive.data && (
        <Alert tone={moveToLive.data.failures.length ? 'warning' : 'success'} className="mb-4">
          Moved {moveToLive.data.moved} commitment{moveToLive.data.moved === 1 ? '' : 's'} to live tracking.
          {moveToLive.data.failures.length > 0 &&
            ` ${moveToLive.data.failures.length} could not be synced (for example, no repository set); open them to fix and retry.`}
        </Alert>
      )}
      {moveToLive.isError && (
        <Alert tone="error" className="mb-4">
          {errorMessage(moveToLive.error)}
        </Alert>
      )}
      {remind.isError && (
        <Alert tone="error" className="mb-4">
          {errorMessage(remind.error)}
        </Alert>
      )}
      {remind.data && (
        <Alert tone="success" className="mb-4">
          {remind.data.message}
        </Alert>
      )}
      {run.isError && (
        <Alert tone="error" className="mb-4">
          {errorMessage(run.error, 'Reconciliation failed.')}
        </Alert>
      )}
      {report?.github_mode === 'simulated' && (
        <Alert tone="info" className="mb-4">
          <span className="inline-flex items-center gap-2">
            <SimulatedBadge /> GitHub is not connected, so states come from simulated events (set them from a commitment's panel, or connect it in Settings).
          </span>
        </Alert>
      )}

      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !report || report.total === 0 ? (
        <EmptyState icon={<RefreshCcw size={20} aria-hidden="true" />} title="No tracked commitments">
          Approve commitments from a meeting first; they appear here once tracked.
        </EmptyState>
      ) : (
        <>
          <dl className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              { label: 'Verified done', value: `${counts!.VERIFIED_DONE} / ${report.total}`, tone: 'text-emerald-700' },
              { label: 'Completion (verified)', value: `${report.completion_rate}%`, tone: 'text-brand' },
              { label: 'Needs attention', value: attention, tone: 'text-rose-700' },
              { label: 'Claimed, unverified', value: counts!.CLAIMED_UNVERIFIED, tone: 'text-amber-700' },
            ].map((card) => (
              <div key={card.label} className="rounded-xl border border-line bg-white p-4">
                <dt className="text-xs font-medium text-muted">{card.label}</dt>
                <dd className={clsx('mt-1 text-2xl font-bold', card.tone)}>{card.value}</dd>
              </div>
            ))}
          </dl>

          <div role="tablist" aria-label="Filter commitments" className="mb-3 flex flex-wrap gap-2">
            {FILTERS.map((f) => {
              const count = f.verdicts ? f.verdicts.reduce((sum, v) => sum + counts![v], 0) : report.total;
              return (
                <button
                  key={f.id}
                  role="tab"
                  type="button"
                  aria-selected={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={clsx(
                    'h-8 rounded-full px-3 text-xs font-semibold',
                    filter === f.id ? 'bg-ink text-white' : 'border border-line bg-white text-body hover:border-line-strong',
                  )}
                >
                  {f.label} ({count})
                </button>
              );
            })}
          </div>

          {items.length === 0 ? (
            <p className="rounded-xl border border-line bg-white px-4 py-8 text-center text-sm text-muted">Nothing in this view.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-line bg-white">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Commitments ordered by risk, highest first</caption>
                <thead className="border-b border-line bg-canvas text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2.5">Verdict</th>
                    <th scope="col" className="px-4 py-2.5">Commitment</th>
                    <th scope="col" className="px-4 py-2.5">Target</th>
                    <th scope="col" className="px-4 py-2.5">Ticket</th>
                    <th scope="col" className="px-4 py-2.5">Why</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {items.map((item) => (
                    <tr key={item.task_id} className="align-top hover:bg-canvas">
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <PriorityBadge priority={item.priority} />
                          <VerdictBadge verdict={item.verdict} />
                        </div>
                        <div className="mt-2 flex items-center gap-1.5" title={`Heuristic risk ${item.risk_score}/100`}>
                          <span className="h-1.5 w-14 overflow-hidden rounded-full bg-line">
                            <span className={clsx('block h-full', RISK_BAR[item.risk_level])} style={{ width: `${item.risk_score}%` }} />
                          </span>
                          <span className="text-[11px] text-muted">{item.risk_level.toLowerCase()}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <button type="button" onClick={() => onOpenTask(item.task_id)} className="text-left font-medium text-ink hover:text-brand hover:underline">
                          {item.description}
                        </button>
                        <div className="text-xs text-muted">
                          {item.assignee}
                          {item.meeting_title && !meetingId && ` · ${item.meeting_title}`}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-body">{timing(item)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs">
                        {item.github_url ? (
                          <a href={item.github_url} target="_blank" rel="noreferrer" className="font-mono text-brand hover:underline">
                            {item.external_key || item.external_ref || 'open'}
                          </a>
                        ) : (
                          <span className="font-mono text-muted">{item.external_key || item.external_ref || '—'}</span>
                        )}
                        <div className="text-muted">{item.github_state ?? 'not checked'}</div>
                      </td>
                      <td className="px-4 py-3 text-xs text-body">{item.risk_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <BriefingModal open={modal === 'briefing'} onClose={() => setModal(null)} meetingId={meetingId} scopeLabel={scopeLabel} />
      <ScheduleModal open={modal === 'schedule'} onClose={() => setModal(null)} meetingId={meetingId} scopeLabel={scopeLabel} />
      <RetryFailedModal open={modal === 'retry'} onClose={() => setModal(null)} failedCount={failedSyncs} meetingId={meetingId} />
    </>
  );
}
