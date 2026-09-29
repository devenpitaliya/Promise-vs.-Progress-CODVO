import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { RetryFailedModal } from './RetryFailedModal';
import { commitmentsApi } from '../../api/endpoints';

vi.mock('../../api/endpoints', () => ({ commitmentsApi: { retryFailed: vi.fn() } }));

function renderModal() {
  const onRetried = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RetryFailedModal open onClose={() => {}} failedCount={16} meetingId={2} onRetried={onRetried} />
    </QueryClientProvider>,
  );
  return onRetried;
}

describe('RetryFailedModal', () => {
  it('retries every failed commitment with the chosen repository and reports the outcome', async () => {
    vi.mocked(commitmentsApi.retryFailed).mockResolvedValue({ retried: 16, synced: 15, failures: [{ task_id: 9, error: 'Jira rejected the credentials.' }] });
    const onRetried = renderModal();

    await userEvent.type(screen.getByLabelText('GitHub repository (optional)'), 'pvp-demo');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Retry 16 commitments' }));

    expect(commitmentsApi.retryFailed).toHaveBeenCalledWith({ meeting_id: 2, repository: 'pvp-demo', create_missing: true });
    expect(await screen.findByText('15 of 16 synced.')).toBeInTheDocument();
    expect(screen.getByText('Jira rejected the credentials.')).toBeInTheDocument();
    expect(onRetried).toHaveBeenCalled();
  });

  it('blocks an invalid repository', async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText('GitHub repository (optional)'), 'not a repo');
    expect(screen.getByText('Use "repo" or "owner/repo".')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry 16 commitments' })).toBeDisabled();
  });
});
