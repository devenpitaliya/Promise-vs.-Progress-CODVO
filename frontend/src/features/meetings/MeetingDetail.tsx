import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Trash2 } from 'lucide-react';

import { ReviewCommitments } from './ReviewCommitments';
import { ReviewSummary } from './ReviewSummary';
import { meetingsApi } from '../../api/endpoints';
import { queryKeys, useInvalidateTracking, useMeeting } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { ApprovalBadge, PriorityBadge, SimulatedBadge, VerificationBadge } from '../../components/ui/Badges';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { ErrorState, LoadingState } from '../../components/ui/States';
import { errorMessage } from '../../lib/api';
import { formatDate, pluralize } from '../../lib/format';
import type { ReviewResult } from '../../types/api';

interface Props {
  meetingId: number;
  onBack: () => void;
  onOpenTask: (id: number) => void;
  onGoToCommitments: () => void;
}

export function MeetingDetail({ meetingId, onBack, onOpenTask, onGoToCommitments }: Props) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateTracking();
  const { data: meeting, isLoading, error, refetch } = useMeeting(meetingId);
  const [reviewing, setReviewing] = useState(false);
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const remove = useMutation({
    mutationFn: () => meetingsApi.remove(meetingId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: queryKeys.meeting(meetingId) });
      await invalidate();
      onBack();
    },
  });

  if (isLoading) return <LoadingState />;
  if (error || !meeting) return <ErrorState error={error} onRetry={() => refetch()} />;

  const pending = meeting.tasks.filter((t) => t.approval_status === 'PENDING').length;
  const refreshMeeting = () => queryClient.invalidateQueries({ queryKey: queryKeys.meeting(meetingId) });

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={onBack} icon={<ArrowLeft size={15} aria-hidden="true" />}>
        Meetings
      </Button>

      <header className="flex flex-col gap-3 border-b border-line pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink">{meeting.title}</h1>
          <p className="mt-1 text-sm text-muted">
            {formatDate(meeting.meeting_date)}
            {meeting.meeting_time && ` · ${meeting.meeting_time}`}
            {meeting.meeting_type && ` · ${meeting.meeting_type}`}
          </p>
          {meeting.participants.length > 0 && (
            <p className="mt-1 text-sm text-body">
              <span className="font-medium">Participants:</span> {meeting.participants.map((p) => p.name).join(', ')}
            </p>
          )}
        </div>
        <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)} icon={<Trash2 size={13} aria-hidden="true" />}>
          Delete meeting
        </Button>
      </header>

      {meeting.summary && (
        <section className="rounded-xl border border-line bg-white p-5">
          <h2 className="mb-1 text-sm font-semibold text-ink">Summary</h2>
          <p className="text-sm text-body">{meeting.summary}</p>
          <p className="mt-2 text-xs text-muted">
            Extracted by {meeting.extraction_source === 'rules' ? 'the rule-based parser' : meeting.extraction_source === 'gemini' ? 'Gemini' : 'OpenAI'}.
            {meeting.trace_url && (
              <>
                {' '}
                <a href={meeting.trace_url} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                  View trace in Langfuse
                </a>
              </>
            )}
          </p>
        </section>
      )}

      {result ? (
        <ReviewSummary
          result={result}
          onViewCommitments={onGoToCommitments}
          onDone={() => {
            setResult(null);
            refreshMeeting();
          }}
        />
      ) : reviewing ? (
        <section aria-labelledby="review-heading" className="space-y-3">
          <h2 id="review-heading" className="text-lg font-semibold text-ink">
            Review {pluralize(pending, 'pending commitment')}
          </h2>
          <ReviewCommitments
            meeting={meeting}
            onCancel={() => setReviewing(false)}
            onDone={(r) => {
              setReviewing(false);
              setResult(r);
            }}
          />
        </section>
      ) : (
        <section aria-labelledby="commitments-heading" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="commitments-heading" className="text-lg font-semibold text-ink">
              {pluralize(meeting.tasks.length, 'commitment')}
            </h2>
            {pending > 0 && <Button onClick={() => setReviewing(true)}>Review {pluralize(pending, 'pending commitment')}</Button>}
          </div>
          {meeting.tasks.length === 0 ? (
            <Alert tone="info">No commitments were found in this transcript.</Alert>
          ) : (
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-white">
              {meeting.tasks.map((task) => (
                <li key={task.id}>
                  <button
                    type="button"
                    onClick={() => onOpenTask(task.id)}
                    className="flex w-full flex-wrap items-center justify-between gap-3 px-5 py-3 text-left hover:bg-canvas"
                  >
                    <span className="min-w-0 text-sm">
                      <span className="font-semibold text-ink">{task.assignee}</span>
                      <span className="text-body"> · {task.description}</span>
                      {task.target_date && <span className="text-muted"> · due {formatDate(task.target_date)}</span>}
                    </span>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <PriorityBadge priority={task.priority} />
                      <ApprovalBadge status={task.approval_status} />
                      {task.approval_status === 'APPROVED' && task.sync_status === 'FAILED' && (
                        <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-800">Sync failed</span>
                      )}
                      {task.sync_status === 'SYNCED' && <VerificationBadge status={task.verification_status} />}
                      {task.is_simulated && <SimulatedBadge />}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <details className="rounded-xl border border-line bg-white p-5">
        <summary className="cursor-pointer text-sm font-semibold text-ink">Transcript</summary>
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-body">{meeting.transcript}</pre>
      </details>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Delete this meeting?"
        description="The transcript and all its commitments will be removed. Issues already created in GitHub are not touched."
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete
            </Button>
          </>
        }
      >
        {remove.isError ? <Alert tone="error">{errorMessage(remove.error)}</Alert> : <p className="text-sm text-body">This cannot be undone.</p>}
      </Modal>
    </div>
  );
}
