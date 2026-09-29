import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { commitmentsApi } from '../../api/endpoints';
import { useInvalidateTracking } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { errorMessage } from '../../lib/api';
import { pluralize } from '../../lib/format';
import type { RetryFailedResult } from '../../types/api';

const REPOSITORY = /^[A-Za-z0-9_.-]+(\/[A-Za-z0-9_.-]+)?$/;

interface Props {
  open: boolean;
  onClose: () => void;
  failedCount: number;
  /** Limit to one meeting; all meetings when omitted. */
  meetingId?: number;
  onRetried?: (result: RetryFailedResult) => void;
}

/** Fix the usual causes of failed syncs (wrong repository, numbers that don't exist) and retry them all at once. */
export function RetryFailedModal({ open, onClose, failedCount, meetingId, onRetried }: Props) {
  const invalidate = useInvalidateTracking();
  const [repository, setRepository] = useState('');
  const [createMissing, setCreateMissing] = useState(false);
  const retry = useMutation({
    mutationFn: () => commitmentsApi.retryFailed({ meeting_id: meetingId, repository: repository.trim() || undefined, create_missing: createMissing }),
    onSuccess: async (result) => {
      await invalidate();
      onRetried?.(result);
    },
  });
  const invalid = repository.trim() !== '' && !REPOSITORY.test(repository.trim());
  const result = retry.data;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Fix and retry failed syncs"
      description={`${pluralize(failedCount, 'commitment')} could not be created or linked in GitHub or Jira.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          <Button onClick={() => retry.mutate()} loading={retry.isPending} disabled={invalid || failedCount === 0}>
            Retry {pluralize(failedCount, 'commitment')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <TextField
          label="GitHub repository (optional)"
          value={repository}
          placeholder="pvp-demo or owner/pvp-demo"
          spellCheck={false}
          maxLength={200}
          error={invalid ? 'Use "repo" or "owner/repo".' : undefined}
          hint="Applied to every failed GitHub commitment. Leave empty to keep each one's repository. 'repo' alone uses your default owner."
          onChange={(e) => setRepository(e.target.value)}
        />
        <label className="flex items-start gap-2 text-sm text-body">
          <input type="checkbox" className="mt-1" checked={createMissing} onChange={(e) => setCreateMissing(e.target.checked)} />
          <span>
            Create new issues instead of linking the issue or PR numbers mentioned in the meeting.
            <span className="block text-xs text-muted">
              Use this when those numbers don't exist in this repository (for example when trying a sample meeting). PRs that can't be linked are tracked as issues.
            </span>
          </span>
        </label>

        {retry.isError && <Alert tone="error">{errorMessage(retry.error)}</Alert>}
        {result && (
          <Alert tone={result.failures.length ? 'warning' : 'success'}>
            <p className="font-medium">
              {result.synced} of {result.retried} synced.
            </p>
            {result.failures.length > 0 && (
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
                {result.failures.slice(0, 6).map((f) => (
                  <li key={f.task_id}>{f.error}</li>
                ))}
                {result.failures.length > 6 && <li>…and {result.failures.length - 6} more</li>}
              </ul>
            )}
          </Alert>
        )}
      </div>
    </Modal>
  );
}
