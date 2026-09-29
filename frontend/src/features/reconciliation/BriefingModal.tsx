import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { briefingsApi } from '../../api/endpoints';
import { queryKeys, useEmails, useSystemStatus } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { TextAreaField, TextField } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { errorMessage } from '../../lib/api';
import { formatDateTime } from '../../lib/format';
import type { EmailStatus } from '../../types/api';

const EMAIL_STATUS: Record<EmailStatus, { label: string; tone: 'success' | 'warning' | 'error' }> = {
  sent: { label: 'Sent', tone: 'success' },
  not_configured: { label: 'Saved, not sent (SMTP not configured)', tone: 'warning' },
  failed: { label: 'Delivery failed', tone: 'error' },
};

interface Props {
  open: boolean;
  onClose: () => void;
  meetingId?: number;
  scopeLabel: string;
}

export function BriefingModal({ open, onClose, meetingId, scopeLabel }: Props) {
  const client = useQueryClient();
  const { data: system } = useSystemStatus();
  const { data: emails = [] } = useEmails();
  const [recipient, setRecipient] = useState('');
  const [instructions, setInstructions] = useState('');

  const preview = useMutation({ mutationFn: () => briefingsApi.preview(meetingId, instructions) });
  const send = useMutation({
    mutationFn: () => briefingsApi.send(recipient.trim(), meetingId, instructions),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.emails }),
  });

  const slack = useMutation({ mutationFn: () => briefingsApi.postToSlack(meetingId, instructions) });

  const shown = send.data?.preview ?? preview.data;
  const sentStatus = send.data ? EMAIL_STATUS[send.data.email.status] : null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="xl"
      title="Pre-meeting briefing"
      description={`Scope: ${scopeLabel}. Figures come from the last reconciliation; run it first for fresh tracker state.`}
      footer={
        <>
          <Button variant="secondary" onClick={() => preview.mutate()} loading={preview.isPending}>
            {shown ? 'Refresh preview' : 'Preview'}
          </Button>
          {system?.slack_connected && (
            <Button variant="secondary" onClick={() => slack.mutate()} loading={slack.isPending}>
              Post to Slack
            </Button>
          )}
          <Button onClick={() => send.mutate()} loading={send.isPending} disabled={!recipient.trim()}>
            Send email
          </Button>
        </>
      }
    >
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-2">
          {!system?.smtp_configured && (
            <Alert tone="warning">SMTP is not configured on the server. Briefings will be saved to history but not delivered.</Alert>
          )}
          <TextField
            label="Recipient email"
            type="email"
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
            placeholder="team-lead@company.com"
            autoComplete="email"
          />
          <TextAreaField
            label="Style notes (optional)"
            rows={3}
            maxLength={1000}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            hint="Tone and focus only, e.g. 'keep it under 5 lines'. Facts always come from verified data."
          />
          {preview.isError && <Alert tone="error">{errorMessage(preview.error)}</Alert>}
          {send.isError && <Alert tone="error">{errorMessage(send.error)}</Alert>}
          {slack.isError && <Alert tone="error">{errorMessage(slack.error)}</Alert>}
          {slack.data && <Alert tone="success">{slack.data.message}</Alert>}
          {sentStatus && send.data && (
            <Alert tone={sentStatus.tone}>
              {sentStatus.label} to {send.data.email.recipient_email}.
              {send.data.email.error && <span className="block text-xs">{send.data.email.error}</span>}
            </Alert>
          )}

          {emails.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold text-ink">Recent briefings</h3>
              <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded-lg border border-line text-xs">
                {emails.slice(0, 10).map((email) => (
                  <li key={email.id} className="flex items-center justify-between gap-2 px-3 py-2">
                    <span className="truncate text-body">{email.recipient_email}</span>
                    <span className="shrink-0 text-muted">
                      {EMAIL_STATUS[email.status].label.split(' (')[0]} · {formatDateTime(email.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="lg:col-span-3">
          {shown ? (
            <div className="space-y-3">
              <p className="text-xs text-muted">
                Subject: <span className="font-medium text-ink">{shown.subject}</span> · narrative by{' '}
                {shown.generated_by === 'rules' ? 'rules (no AI key)' : shown.generated_by === 'gemini' ? 'Gemini' : 'OpenAI'}
              </p>
              {/* sandbox="" blocks scripts, forms and same-origin access in the rendered email. */}
              <iframe
                title="Email preview"
                sandbox=""
                srcDoc={shown.html}
                className="h-[28rem] w-full rounded-lg border border-line bg-white"
              />
            </div>
          ) : (
            <div className="flex h-full min-h-[16rem] items-center justify-center rounded-lg border border-dashed border-line-strong text-sm text-muted">
              Preview the briefing to see exactly what will be sent.
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
