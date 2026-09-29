import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';

import { briefingsApi } from '../../api/endpoints';
import { queryKeys, useSchedules, useSystemStatus } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { errorMessage } from '../../lib/api';
import { browserTimezone, formatDate, formatDateTime, todayIso } from '../../lib/format';
import type { AuditRunResult, ScheduleType, ScheduledAudit } from '../../types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  meetingId?: number;
  scopeLabel: string;
}

function describe(audit: ScheduledAudit): string {
  if (audit.schedule_type === 'single') return `Once, ${formatDateTime(audit.run_at)}`;
  return `Daily at ${audit.daily_time} (${audit.timezone}), ${formatDate(audit.start_date)} – ${formatDate(audit.end_date)}`;
}

function destinations(audit: ScheduledAudit): string {
  return [audit.recipient_email, audit.post_to_slack ? 'Slack' : null].filter(Boolean).join(' and ');
}

function runSummary(result: AuditRunResult): { ok: boolean; text: string } {
  const parts: string[] = [];
  let ok = true;
  if (result.email) {
    const status = result.email.status;
    parts.push(`Email ${status === 'sent' ? 'sent' : status === 'not_configured' ? 'saved but not sent (SMTP not configured)' : 'failed'}.`);
    ok = ok && status === 'sent';
  }
  if (result.slack_ok !== null) {
    parts.push(result.slack_ok ? 'Posted to Slack.' : `Slack failed: ${result.slack_message}`);
    ok = ok && result.slack_ok;
  }
  return { ok, text: `Audit ran. ${parts.join(' ')}` };
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

export function ScheduleModal({ open, onClose, meetingId, scopeLabel }: Props) {
  const client = useQueryClient();
  const { data: schedules = [] } = useSchedules();
  const { data: system } = useSystemStatus();
  const timezone = browserTimezone();

  const [type, setType] = useState<ScheduleType>('recurring');
  const [recipient, setRecipient] = useState('');
  const [toSlack, setToSlack] = useState(false);
  const [runAt, setRunAt] = useState('');
  const [startDate, setStartDate] = useState(todayIso());
  const [endDate, setEndDate] = useState(addDays(todayIso(), 13));
  const [dailyTime, setDailyTime] = useState('09:00');

  const refresh = () => client.invalidateQueries({ queryKey: queryKeys.schedules });
  const create = useMutation({ mutationFn: briefingsApi.createSchedule, onSuccess: refresh });
  const cancel = useMutation({ mutationFn: briefingsApi.cancelSchedule, onSuccess: refresh });
  const runNow = useMutation({
    mutationFn: briefingsApi.runSchedule,
    onSettled: () => Promise.all([refresh(), client.invalidateQueries({ queryKey: queryKeys.emails })]),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const delivery = { recipient_email: recipient.trim() || undefined, post_to_slack: toSlack };
    create.mutate(
      type === 'single'
        ? { ...delivery, schedule_type: 'single', timezone, run_at: new Date(runAt).toISOString(), meeting_id: meetingId }
        : {
            ...delivery,
            schedule_type: 'recurring',
            timezone,
            start_date: startDate,
            end_date: endDate,
            daily_time: dailyTime,
            meeting_id: meetingId,
          },
    );
  };

  const error = create.error || cancel.error || runNow.error;

  return (
    <Modal open={open} onClose={onClose} size="lg" title="Scheduled pre-meeting audits" description={`Scope: ${scopeLabel}. Each run checks the trackers, then sends the briefing by email, to Slack, or both.`}>
      <div className="space-y-6">
        {system && !system.scheduler_running && (
          <Alert tone="warning">The scheduler is not running on this server, so schedules will not fire automatically. "Run now" still works.</Alert>
        )}
        {error && <Alert tone="error">{errorMessage(error)}</Alert>}
        {runNow.data && <Alert tone={runSummary(runNow.data).ok ? 'success' : 'warning'}>{runSummary(runNow.data).text}</Alert>}

        <form onSubmit={submit} className="space-y-4 rounded-xl border border-line p-4">
          <div role="radiogroup" aria-label="Schedule type" className="inline-flex rounded-lg border border-line p-0.5">
            {(['recurring', 'single'] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={type === value}
                onClick={() => setType(value)}
                className={clsx('h-8 rounded-md px-3 text-sm font-medium', type === value ? 'bg-brand text-white' : 'text-muted hover:text-ink')}
              >
                {value === 'recurring' ? 'Every day in a range' : 'Once'}
              </button>
            ))}
          </div>
          <TextField label="Email to (optional with Slack)" type="email" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="team-lead@company.com" />
          <label className={clsx('flex items-center gap-2 text-sm', system?.slack_connected ? 'text-body' : 'text-subtle')}>
            <input type="checkbox" checked={toSlack} disabled={!system?.slack_connected} onChange={(e) => setToSlack(e.target.checked)} />
            Also post to Slack
            {!system?.integrations_available?.includes('slack') ? (
              <span className="rounded-full bg-brand-soft px-1.5 text-[11px] font-semibold text-brand">Coming soon</span>
            ) : (
              !system?.slack_connected && <span className="text-xs">(connect Slack in Settings first)</span>
            )}
          </label>
          {type === 'single' ? (
            <TextField label="Run at" type="datetime-local" required value={runAt} onChange={(e) => setRunAt(e.target.value)} hint={`Your timezone: ${timezone}`} />
          ) : (
            <div className="grid gap-3 sm:grid-cols-3">
              <TextField label="From" type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              <TextField label="To" type="date" required value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} />
              <TextField label="Time" type="time" required value={dailyTime} onChange={(e) => setDailyTime(e.target.value)} hint={timezone} />
            </div>
          )}
          <div className="flex justify-end">
            <Button type="submit" loading={create.isPending} disabled={(!recipient.trim() && !toSlack) || (type === 'single' && !runAt)}>
              Create schedule
            </Button>
          </div>
        </form>

        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink">Schedules</h3>
          {schedules.length === 0 ? (
            <p className="text-sm text-muted">No schedules yet.</p>
          ) : (
            <ul className="divide-y divide-line rounded-xl border border-line">
              {schedules.map((audit) => (
                <li key={audit.id} className="flex flex-col gap-2 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="font-medium text-ink">{describe(audit)}</div>
                    <div className="text-xs text-muted">
                      To {destinations(audit)} · {audit.status}
                      {audit.next_run_at && ` · next ${formatDateTime(audit.next_run_at)}`} · {audit.runs_count} run(s)
                    </div>
                    {audit.last_error && <div className="text-xs text-rose-700">Last run: {audit.last_error}</div>}
                  </div>
                  {audit.status === 'active' && (
                    <div className="flex shrink-0 gap-2">
                      <Button size="sm" variant="secondary" loading={runNow.isPending && runNow.variables === audit.id} onClick={() => runNow.mutate(audit.id)}>
                        Run now
                      </Button>
                      <Button size="sm" variant="danger" loading={cancel.isPending && cancel.variables === audit.id} onClick={() => cancel.mutate(audit.id)}>
                        Cancel
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}
