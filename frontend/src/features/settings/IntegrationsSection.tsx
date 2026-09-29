import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { GitBranch, MessageSquare, SquareKanban } from 'lucide-react';

import { integrationsApi } from '../../api/endpoints';
import { queryKeys, useIntegrations } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { ErrorState, LoadingState } from '../../components/ui/States';
import { errorMessage } from '../../lib/api';
import { formatDateTime } from '../../lib/format';
import type { Integration, TrackerKind } from '../../types/api';

const ABOUT: Record<string, { Icon: typeof GitBranch; text: string }> = {
  github: { Icon: GitBranch, text: 'Creates or links issues and pull requests, and checks whether they were really merged or completed.' },
  jira: { Icon: SquareKanban, text: 'Creates or links Jira issues and checks their status category, so custom workflows work as-is.' },
  slack: { Icon: MessageSquare, text: 'Posts pre-meeting briefings and due-date reminders to a channel. Testing sends a short message.' },
};

function connectionLabel(integration: Integration): { text: string; className: string } {
  if (integration.source === 'user') return { text: 'Connected', className: 'border-emerald-200 bg-emerald-50 text-emerald-800' };
  if (integration.source === 'server') return { text: 'Server default', className: 'border-sky-200 bg-sky-50 text-sky-800' };
  if (integration.category === 'tracker') return { text: 'Simulated', className: 'border-violet-200 bg-violet-50 text-violet-800' };
  return { text: 'Not connected', className: 'border-line bg-canvas text-muted' };
}

function ComingSoonCard({ integration }: { integration: Integration }) {
  const { Icon, text } = ABOUT[integration.kind] ?? { Icon: GitBranch, text: '' };
  return (
    <section className="rounded-xl border border-dashed border-line bg-canvas p-5 opacity-80" aria-labelledby={`integration-${integration.kind}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-white text-muted">
            <Icon size={16} aria-hidden="true" />
          </span>
          <div>
            <h3 id={`integration-${integration.kind}`} className="font-semibold text-ink">
              {integration.label}
            </h3>
            <p className="max-w-prose text-xs text-muted">{text}</p>
          </div>
        </div>
        <span className="rounded-full border border-brand/30 bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand">Coming soon</span>
      </div>
      <p className="mt-3 text-sm text-muted">We're adding {integration.label} soon. For now, commitments are tracked in GitHub.</p>
    </section>
  );
}

function IntegrationCard({ integration }: { integration: Integration }) {
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(integration.fields.map((f) => [f.name, f.secret ? '' : (integration.config[f.name] ?? '')])),
  );
  const refresh = () =>
    Promise.all([client.invalidateQueries({ queryKey: queryKeys.integrations }), client.invalidateQueries({ queryKey: queryKeys.system })]);

  const test = useMutation({ mutationFn: () => integrationsApi.test(integration.kind), onSettled: refresh });
  const save = useMutation({
    mutationFn: () => integrationsApi.save(integration.kind, values),
    onSuccess: async () => {
      setValues((current) => Object.fromEntries(Object.entries(current).map(([k, v]) => [k, integration.fields.find((f) => f.name === k)?.secret ? '' : v])));
      await refresh();
      test.mutate(); // prove the saved connection works straight away
    },
  });
  const disconnect = useMutation({
    mutationFn: () => integrationsApi.disconnect(integration.kind),
    onSuccess: () => {
      setValues(Object.fromEntries(integration.fields.map((f) => [f.name, ''])));
      test.reset();
      return refresh();
    },
  });

  const status = connectionLabel(integration);
  const { Icon, text } = ABOUT[integration.kind] ?? { Icon: GitBranch, text: '' };
  const result = test.data ?? (integration.last_test_ok === null ? null : { ok: integration.last_test_ok, message: integration.last_test_message ?? '', tested_at: integration.last_tested_at ?? '' });
  const error = save.error || disconnect.error || test.error;

  return (
    <section className="space-y-4 rounded-xl border border-line bg-white p-5" aria-labelledby={`integration-${integration.kind}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-canvas text-ink">
            <Icon size={16} aria-hidden="true" />
          </span>
          <div>
            <h3 id={`integration-${integration.kind}`} className="font-semibold text-ink">
              {integration.label}
            </h3>
            <p className="max-w-prose text-xs text-muted">{text}</p>
          </div>
        </div>
        <span className={clsx('rounded-full border px-2 py-0.5 text-xs font-semibold', status.className)}>{status.text}</span>
      </div>

      {integration.source === 'server' && (
        <p className="text-sm text-body">Using the server-wide connection from the administrator. Add your own below to use your account instead.</p>
      )}
      {integration.source === 'none' && integration.category === 'tracker' && (
        <p className="text-sm text-body">Not connected: {integration.label} commitments are tracked in a clearly labelled simulation.</p>
      )}

      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {integration.fields.map((field) => {
          const saved = integration.secrets_masked[field.name];
          return (
            <TextField
              key={field.name}
              label={`${field.label}${field.required ? '' : ' (optional)'}`}
              type={field.secret ? 'password' : 'text'}
              autoComplete="off"
              spellCheck={false}
              value={values[field.name] ?? ''}
              placeholder={field.secret && saved ? `Saved (${saved}); leave empty to keep` : field.placeholder}
              hint={field.help || undefined}
              maxLength={500}
              onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
            />
          );
        })}

        <div className="sm:col-span-2 space-y-3">
          {result && (
            <Alert tone={result.ok ? 'success' : 'error'}>
              {result.message}
              {result.tested_at && <span className="ml-1 text-xs opacity-75">({formatDateTime(result.tested_at)})</span>}
            </Alert>
          )}
          {error && <Alert tone="error">{errorMessage(error)}</Alert>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={save.isPending}>
              {integration.has_user_connection ? 'Save and test' : 'Connect and test'}
            </Button>
            <Button variant="secondary" onClick={() => test.mutate()} loading={test.isPending && !save.isPending} disabled={integration.source === 'none'}>
              Test connection
            </Button>
            {integration.has_user_connection && (
              <Button variant="danger" onClick={() => disconnect.mutate()} loading={disconnect.isPending}>
                Disconnect
              </Button>
            )}
          </div>
        </div>
      </form>
    </section>
  );
}

function DefaultTracker({ value, jiraReady, jiraAvailable }: { value: TrackerKind; jiraReady: boolean; jiraAvailable: boolean }) {
  const client = useQueryClient();
  const change = useMutation({
    mutationFn: integrationsApi.setDefaultTracker,
    onSuccess: (data) => {
      client.setQueryData(queryKeys.integrations, data);
      return client.invalidateQueries({ queryKey: queryKeys.system });
    },
  });
  const options: { id: TrackerKind; label: string; disabled?: boolean }[] = [
    { id: 'github', label: 'GitHub issues' },
    { id: 'jira', label: !jiraAvailable ? 'Jira (coming soon)' : jiraReady ? 'Jira issues' : 'Jira issues (simulated)', disabled: !jiraAvailable },
  ];
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-4">
      <div>
        <div className="text-sm font-semibold text-ink">Default tracker for new tickets</div>
        <p className="text-xs text-muted">Where extracted commitments go unless the meeting names a PR or a Jira key. You can change it per commitment in review.</p>
      </div>
      <div role="radiogroup" aria-label="Default tracker" className="inline-flex rounded-lg border border-line p-0.5">
        {options.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={value === o.id}
            disabled={change.isPending || o.disabled}
            onClick={() => change.mutate(o.id)}
            className={clsx(
              'h-8 rounded-md px-3 text-xs font-semibold disabled:cursor-not-allowed',
              value === o.id ? 'bg-ink text-white' : o.disabled ? 'text-subtle' : 'text-muted hover:text-ink',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
      {change.error && <Alert tone="error" className="w-full">{errorMessage(change.error)}</Alert>}
    </div>
  );
}

export function IntegrationsSection() {
  const { data, isLoading, error, refetch } = useIntegrations();
  if (isLoading) return <LoadingState />;
  if (error || !data) return <ErrorState error={error} onRetry={() => refetch()} />;
  const jira = data.integrations.find((i) => i.kind === 'jira');

  return (
    <section aria-labelledby="integrations-title" className="space-y-4">
      <div>
        <h2 id="integrations-title" className="text-lg font-semibold text-ink">
          Integrations
        </h2>
        <p className="text-sm text-muted">
          Connect your own tools. Credentials are encrypted and only used for your workspace; secrets are never shown again in full.
        </p>
      </div>
      <DefaultTracker value={data.default_tracker} jiraReady={jira?.mode === 'live'} jiraAvailable={jira?.available ?? false} />
      {data.integrations.map((integration) =>
        integration.available ? (
          <IntegrationCard key={`${integration.kind}-${integration.has_user_connection}`} integration={integration} />
        ) : (
          <ComingSoonCard key={integration.kind} integration={integration} />
        ),
      )}
    </section>
  );
}
