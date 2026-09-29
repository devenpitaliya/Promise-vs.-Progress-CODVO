import { useState } from 'react';
import { CheckCircle2 } from 'lucide-react';

import { RetryFailedModal } from '../commitments/RetryFailedModal';

import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { SimulatedBadge } from '../../components/ui/Badges';
import { pluralize } from '../../lib/format';
import type { ReviewResult } from '../../types/api';

interface Props {
  result: ReviewResult;
  onViewCommitments: () => void;
  onDone: () => void;
}

export function ReviewSummary({ result, onViewCommitments, onDone }: Props) {
  const failed = new Map(result.sync_failures.map((f) => [f.task_id, f.error]));
  const synced = result.approved.filter((t) => !failed.has(t.id));
  const simulated = synced.some((t) => t.is_simulated);
  const [fixing, setFixing] = useState(false);
  const [stillFailing, setStillFailing] = useState<number | null>(null);
  const meetingId = result.approved[0]?.meeting_id;

  return (
    <div className="space-y-5 rounded-xl border border-line bg-white p-6">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 text-emerald-600" size={22} aria-hidden="true" />
        <div>
          <h2 className="text-lg font-semibold text-ink">Review saved</h2>
          <p className="text-sm text-muted">
            {pluralize(result.approved.length, 'commitment')} approved, {result.rejected_ids.length} rejected.
          </p>
        </div>
      </div>

      {synced.length > 0 && (
        <div>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
            Now tracked {simulated && <SimulatedBadge />}
          </h3>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {synced.map((task) => (
              <li key={task.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="text-ink">
                  <span className="font-medium">{task.assignee}</span> · {task.description}
                </span>
                {task.github_url ? (
                  <a href={task.github_url} target="_blank" rel="noreferrer" className="font-mono text-xs text-brand hover:underline">
                    {task.external_ref || `#${task.github_issue_number ?? task.github_pr_number}`}
                  </a>
                ) : (
                  <span className="font-mono text-xs text-muted">{task.external_ref || 'new issue'}</span>
                )}
              </li>
            ))}
          </ul>
          {simulated && (
            <p className="mt-2 text-xs text-muted">
              GitHub is in simulation mode, so no real issues were created. Connect GitHub in Settings → Integrations to sync for real.
            </p>
          )}
        </div>
      )}

      {result.sync_failures.length > 0 && (
        <Alert tone="warning">
          <p className="font-medium">{pluralize(result.sync_failures.length, 'commitment')} could not be synced:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {result.approved
              .filter((t) => failed.has(t.id))
              .map((t) => (
                <li key={t.id}>
                  <span className="font-medium">{t.description}</span>: {failed.get(t.id)}
                </li>
              ))}
          </ul>
          <p className="mt-1">They stay approved. Fix the repository or reference and retry them all at once, or one by one from the commitment panel.</p>
          <Button className="mt-2" size="sm" onClick={() => setFixing(true)}>
            Fix and retry
          </Button>
          {stillFailing !== null && (
            <p className="mt-2 text-xs">{stillFailing === 0 ? 'All retried commitments are now synced.' : `${stillFailing} still failing; see the details in the dialog.`}</p>
          )}
        </Alert>
      )}
      <RetryFailedModal
        open={fixing}
        onClose={() => setFixing(false)}
        failedCount={stillFailing ?? result.sync_failures.length}
        meetingId={meetingId}
        onRetried={(r) => setStillFailing(r.failures.length)}
      />

      <div className="flex flex-wrap gap-2">
        <Button onClick={onViewCommitments}>View commitments</Button>
        <Button variant="secondary" onClick={onDone}>
          Back to meeting
        </Button>
      </div>
    </div>
  );
}
