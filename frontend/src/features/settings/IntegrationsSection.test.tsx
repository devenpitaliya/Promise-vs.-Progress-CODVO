import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { IntegrationsSection } from './IntegrationsSection';
import { integrationsApi } from '../../api/endpoints';
import type { Integration, IntegrationsResponse } from '../../types/api';

vi.mock('../../api/endpoints', () => ({
  integrationsApi: { list: vi.fn(), save: vi.fn(), test: vi.fn(), disconnect: vi.fn(), setDefaultTracker: vi.fn() },
}));

const api = vi.mocked(integrationsApi);

function jira(overrides: Partial<Integration> = {}): Integration {
  return {
    kind: 'jira',
    label: 'Jira',
    category: 'tracker',
    available: true,
    fields: [
      { name: 'base_url', label: 'Site URL', secret: false, required: true, placeholder: 'https://your-team.atlassian.net', help: '' },
      { name: 'api_token', label: 'API token', secret: true, required: true, placeholder: 'ATATT...', help: '' },
    ],
    source: 'none',
    mode: 'simulated',
    has_user_connection: false,
    config: {},
    secrets_masked: { api_token: null },
    last_tested_at: null,
    last_test_ok: null,
    last_test_message: null,
    ...overrides,
  };
}

function renderSection(response: IntegrationsResponse) {
  api.list.mockResolvedValue(response);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IntegrationsSection />
    </QueryClientProvider>,
  );
}

describe('IntegrationsSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('connects a tool, then immediately tests the saved connection', async () => {
    renderSection({ integrations: [jira()], default_tracker: 'github' });
    const card = await screen.findByRole('region', { name: 'Jira' });
    expect(within(card).getByText('Simulated')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Test connection' })).toBeDisabled();

    api.save.mockResolvedValue(jira({ source: 'user', mode: 'live', has_user_connection: true }));
    api.test.mockResolvedValue({ ok: true, message: 'Connected as Maya Chen', tested_at: '2026-09-29T10:00:00Z' });
    await userEvent.type(within(card).getByLabelText('Site URL'), 'https://acme.atlassian.net');
    await userEvent.type(within(card).getByLabelText('API token'), 'ATATT-secret');
    await userEvent.click(within(card).getByRole('button', { name: 'Connect and test' }));

    await waitFor(() => expect(api.test).toHaveBeenCalledWith('jira'));
    expect(api.save).toHaveBeenCalledWith('jira', { base_url: 'https://acme.atlassian.net', api_token: 'ATATT-secret' });
    expect(await screen.findByText(/Connected as Maya Chen/)).toBeInTheDocument();
  });

  it('never prefills saved secrets and offers to disconnect', async () => {
    renderSection({
      integrations: [jira({ source: 'user', mode: 'live', has_user_connection: true, config: { base_url: 'https://acme.atlassian.net' }, secrets_masked: { api_token: 'ATAT****cret' } })],
      default_tracker: 'jira',
    });
    const card = await screen.findByRole('region', { name: 'Jira' });
    expect(within(card).getByLabelText('Site URL')).toHaveValue('https://acme.atlassian.net');
    const token = within(card).getByLabelText('API token');
    expect(token).toHaveValue('');
    expect(token).toHaveAttribute('placeholder', expect.stringContaining('ATAT****cret'));
    expect(within(card).getByRole('button', { name: 'Disconnect' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Jira issues' })).toHaveAttribute('aria-checked', 'true');
  });

  it('shows tools that are not enabled yet as coming soon, with no form', async () => {
    renderSection({ integrations: [jira({ available: false })], default_tracker: 'github' });
    const card = await screen.findByRole('region', { name: 'Jira' });
    expect(within(card).getByText('Coming soon')).toBeInTheDocument();
    expect(within(card).queryByRole('button')).not.toBeInTheDocument();
    expect(within(card).queryByLabelText('API token')).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Jira (coming soon)' })).toBeDisabled();
  });
});
