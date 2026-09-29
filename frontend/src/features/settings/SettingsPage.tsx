import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, CircleSlash } from 'lucide-react';

import { IntegrationsSection } from './IntegrationsSection';
import { settingsApi } from '../../api/endpoints';
import { queryKeys, useAiSettings, useSystemStatus } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { ErrorState, LoadingState, PageHeader } from '../../components/ui/States';
import { errorMessage } from '../../lib/api';
import type { AiSettings, LlmProvider } from '../../types/api';

const PROVIDERS: { id: LlmProvider; name: string; placeholder: string }[] = [
  { id: 'gemini', name: 'Google Gemini', placeholder: 'AIza…' },
  { id: 'openai', name: 'OpenAI', placeholder: 'sk-…' },
];

function ProviderCard({ provider, settings }: { provider: (typeof PROVIDERS)[number]; settings: AiSettings }) {
  const client = useQueryClient();
  const [key, setKey] = useState('');
  const masked = provider.id === 'gemini' ? settings.gemini_key_masked : settings.openai_key_masked;
  const model = provider.id === 'gemini' ? settings.gemini_model : settings.openai_model;
  const serverKey = provider.id === 'gemini' ? settings.server_gemini_available : settings.server_openai_available;
  const field = provider.id === 'gemini' ? 'gemini_api_key' : 'openai_api_key';

  const onSaved = (updated: AiSettings) => {
    client.setQueryData(queryKeys.aiSettings, updated);
    setKey('');
  };
  const save = useMutation({ mutationFn: (value: string) => settingsApi.updateAi({ [field]: value, preferred_provider: value ? provider.id : undefined }), onSuccess: onSaved });
  const test = useMutation({ mutationFn: () => settingsApi.testKey(provider.id, key.trim()) });
  const prefer = useMutation({ mutationFn: () => settingsApi.updateAi({ preferred_provider: provider.id }), onSuccess: onSaved });

  return (
    <section className="space-y-4 rounded-xl border border-line bg-white p-5" aria-labelledby={`${provider.id}-title`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id={`${provider.id}-title`} className="font-semibold text-ink">
            {provider.name}
          </h2>
          <p className="text-xs text-muted">Model: {model}</p>
        </div>
        {settings.active_provider === provider.id && (
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">In use</span>
        )}
      </div>

      <p className="text-sm text-body">
        {masked ? (
          <>
            Your key: <code className="font-mono text-xs">{masked}</code>
          </>
        ) : serverKey ? (
          'Using the server-wide key. Add your own to use your account instead.'
        ) : (
          'No key configured.'
        )}
      </p>

      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(key.trim());
        }}
      >
        <TextField
          label={masked ? 'Replace key' : 'API key'}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={key}
          onChange={(e) => {
            setKey(e.target.value);
            test.reset();
          }}
          placeholder={provider.placeholder}
          hint="Stored encrypted and only used for your workspace. It is never shown again in full."
        />
        {test.data && <Alert tone={test.data.valid ? 'success' : 'error'}>{test.data.message}</Alert>}
        {(save.error || test.error || prefer.error) && <Alert tone="error">{errorMessage(save.error || test.error || prefer.error)}</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => test.mutate()} loading={test.isPending} disabled={key.trim().length < 10}>
            Test key
          </Button>
          <Button type="submit" loading={save.isPending && !!key} disabled={key.trim().length < 10}>
            Save key
          </Button>
          {masked && (
            <Button variant="danger" onClick={() => save.mutate('')} loading={save.isPending && !key}>
              Remove key
            </Button>
          )}
          {masked && settings.active_provider !== provider.id && (
            <Button variant="ghost" onClick={() => prefer.mutate()} loading={prefer.isPending}>
              Use this provider
            </Button>
          )}
        </div>
      </form>
    </section>
  );
}

function StatusRow({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <li className="flex items-start gap-3 py-3">
      {ok ? (
        <CheckCircle2 size={18} className="mt-0.5 text-emerald-600" aria-label="Configured" />
      ) : (
        <CircleSlash size={18} className="mt-0.5 text-subtle" aria-label="Not configured" />
      )}
      <div>
        <div className="text-sm font-medium text-ink">{label}</div>
        <div className="text-xs text-muted">{detail}</div>
      </div>
    </li>
  );
}

export function SettingsPage() {
  const { data: ai, isLoading, error, refetch } = useAiSettings();
  const { data: system } = useSystemStatus();

  return (
    <>
      <PageHeader title="Settings" description="AI providers for extraction and briefings, the tools you connect, and the status of this server." />
      {isLoading ? (
        <LoadingState />
      ) : error || !ai ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            {ai.active_provider === 'rules' && (
              <Alert tone="warning">
                No AI key is configured, so commitments are extracted with a transparent rule-based parser. It works best with
                "Name: sentence" transcripts and explicit references like "PR #12".
              </Alert>
            )}
            {PROVIDERS.map((provider) => (
              <ProviderCard key={provider.id} provider={provider} settings={ai} />
            ))}
            <div className="pt-4">
              <IntegrationsSection />
            </div>
          </div>
          <section className="h-fit rounded-xl border border-line bg-white p-5" aria-labelledby="system-title">
            <h2 id="system-title" className="font-semibold text-ink">
              Status
            </h2>
            <p className="text-xs text-muted">What is active for your workspace right now.</p>
            {system && (
              <ul className="mt-2 divide-y divide-line">
                <StatusRow
                  ok={system.github_mode === 'live'}
                  label={system.github_mode === 'live' ? 'GitHub: live' : 'GitHub: simulated'}
                  detail={system.github_mode === 'live' ? 'Issues are created and verified in real repositories.' : 'Not connected; GitHub state is simulated.'}
                />
                {system.integrations_available.includes('jira') ? (
                  <StatusRow
                    ok={system.jira_mode === 'live'}
                    label={system.jira_mode === 'live' ? 'Jira: live' : 'Jira: simulated'}
                    detail={system.jira_mode === 'live' ? 'Jira issues are created and verified in your site.' : 'Not connected; Jira state is simulated.'}
                  />
                ) : (
                  <StatusRow ok={false} label="Jira: coming soon" detail="Commitments are tracked in GitHub for now." />
                )}
                {system.integrations_available.includes('slack') ? (
                  <StatusRow
                    ok={system.slack_connected}
                    label="Slack"
                    detail={system.slack_connected ? 'Briefings and reminders can be posted to Slack.' : 'Not connected.'}
                  />
                ) : (
                  <StatusRow ok={false} label="Slack: coming soon" detail="Briefings are sent by email for now." />
                )}
                <StatusRow
                  ok
                  label={`New tickets go to ${system.default_tracker === 'jira' ? 'Jira' : 'GitHub'}`}
                  detail="Change the default tracker under Integrations."
                />
                <StatusRow
                  ok={system.smtp_configured}
                  label="Email delivery"
                  detail={system.smtp_configured ? 'Briefings are sent via SMTP.' : 'SMTP not configured; briefings are saved but not sent.'}
                />
                <StatusRow
                  ok={system.scheduler_running}
                  label="Scheduler"
                  detail={system.scheduler_running ? 'Scheduled audits and hourly GitHub checks are running.' : 'Background jobs are disabled on this instance.'}
                />
                <StatusRow
                  ok={system.tracing_enabled}
                  label={system.tracing_enabled ? 'LLM tracing: Langfuse' : 'LLM tracing: off'}
                  detail={
                    system.tracing_enabled
                      ? `Traces, tokens and cost are sent to ${system.tracing_url}.`
                      : `Langfuse is off (${system.tracing_off_reason ?? 'not configured'}). Set LANGFUSE_ENABLED in .env.`
                  }
                />
                <StatusRow ok label="Timezone" detail={`Due dates are evaluated in ${system.app_timezone}.`} />
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}
