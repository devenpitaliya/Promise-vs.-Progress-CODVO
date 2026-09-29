import { api } from '../lib/api';
import type {
  AiSettings,
  PublicConfig,
  BriefingPreview,
  AuditRunResult,
  ConvertedTranscript,
  EmailLog,
  Integration,
  IntegrationsResponse,
  IntegrationTestResult,
  SlackPostResult,
  TrackerKind,
  LlmProvider,
  Meeting,
  MeetingCreate,
  MeetingListItem,
  Participant,
  ReconciliationReport,
  ReviewResult,
  RetryFailedResult,
  SampleTranscript,
  SimulatedSyncResult,
  ScheduleAuditRequest,
  ScheduledAudit,
  SystemStatus,
  Task,
  TaskCreate,
  TaskUpdate,
  TokenResponse,
  User,
} from '../types/api';

const data = <T>(promise: Promise<{ data: T }>): Promise<T> => promise.then((r) => r.data);

export const configApi = {
  get: () => data<PublicConfig>(api.get('/config')),
};

export const authApi = {
  login: (email: string, password: string) => data<TokenResponse>(api.post('/auth/login', { email, password })),
  register: (email: string, password: string, full_name: string) =>
    data<TokenResponse>(api.post('/auth/register', { email, password, full_name })),
  demo: () => data<TokenResponse>(api.post('/auth/demo')),
  me: () => data<User>(api.get('/auth/me')),
};

export const meetingsApi = {
  list: () => data<MeetingListItem[]>(api.get('/meetings/')),
  get: (id: number) => data<Meeting>(api.get(`/meetings/${id}`)),
  create: (payload: MeetingCreate) => data<Meeting>(api.post('/meetings/', payload)),
  remove: (id: number) => api.delete(`/meetings/${id}`),
  samples: () => data<SampleTranscript[]>(api.get('/meetings/samples')),
  participants: () => data<Participant[]>(api.get('/meetings/participants')),
  convertTranscript: (text: string) => data<ConvertedTranscript>(api.post('/meetings/transcript/convert', { text })),
};

export const commitmentsApi = {
  list: (params: { meeting_id?: number; approval_status?: string } = {}) =>
    data<Task[]>(api.get('/commitments/', { params })),
  get: (id: number) => data<Task>(api.get(`/commitments/${id}`)),
  search: (q: string) =>
    data<{ available: boolean; results: { score: number; task: Task }[] }>(api.get('/commitments/search', { params: { q } })),
  create: (payload: TaskCreate) => data<Task>(api.post('/commitments/', payload)),
  update: (id: number, payload: TaskUpdate) => data<Task>(api.patch(`/commitments/${id}`, payload)),
  remove: (id: number) => api.delete(`/commitments/${id}`),
  review: (meetingId: number, approveIds: number[], rejectIds: number[], defaultRepository?: string) =>
    data<ReviewResult>(
      api.post(
        '/commitments/review',
        { approve_ids: approveIds, reject_ids: rejectIds, default_repository: defaultRepository || null },
        { params: { meeting_id: meetingId } },
      ),
    ),
  retrySync: (id: number) => data<Task>(api.post(`/commitments/${id}/sync`, undefined, { timeout: 60_000 })),
  retryFailed: (payload: { meeting_id?: number; repository?: string; create_missing?: boolean }) =>
    data<RetryFailedResult>(api.post('/commitments/retry-failed', payload, { timeout: 120_000 })),
  syncSimulated: () => data<SimulatedSyncResult>(api.post('/commitments/sync-simulated', undefined, { timeout: 120_000 })),
  simulate: (id: number, state: 'open' | 'merged' | 'closed' | 'closed_not_planned') =>
    data<Task>(api.post(`/commitments/${id}/simulate`, { state })),
};

export const reconciliationApi = {
  report: (meetingId?: number) =>
    data<ReconciliationReport>(api.get('/reconciliation/report', { params: meetingId ? { meeting_id: meetingId } : {} })),
  run: (meetingId?: number) =>
    data<ReconciliationReport>(api.post('/reconciliation/run', { meeting_id: meetingId ?? null }, { timeout: 120_000 })),
  remindOnSlack: (meetingId?: number) =>
    data<SlackPostResult>(api.post('/reconciliation/reminders/slack', undefined, { params: meetingId ? { meeting_id: meetingId } : {}, timeout: 60_000 })),
};

export const briefingsApi = {
  preview: (meetingId?: number, customInstructions?: string) =>
    data<BriefingPreview>(
      api.post('/briefings/preview', { meeting_id: meetingId ?? null, custom_instructions: customInstructions || null }),
    ),
  send: (recipientEmail: string, meetingId?: number, customInstructions?: string) =>
    data<{ email: EmailLog; preview: BriefingPreview }>(
      api.post('/briefings/send', {
        recipient_email: recipientEmail,
        meeting_id: meetingId ?? null,
        custom_instructions: customInstructions || null,
      }),
    ),
  emails: () => data<EmailLog[]>(api.get('/briefings/emails')),
  schedules: () => data<ScheduledAudit[]>(api.get('/briefings/schedules')),
  createSchedule: (payload: ScheduleAuditRequest) => data<ScheduledAudit>(api.post('/briefings/schedules', payload)),
  cancelSchedule: (id: number) => data<ScheduledAudit>(api.delete(`/briefings/schedules/${id}`)),
  postToSlack: (meetingId?: number, customInstructions?: string) =>
    data<SlackPostResult>(
      api.post('/briefings/slack', { meeting_id: meetingId ?? null, custom_instructions: customInstructions || null }, { timeout: 120_000 }),
    ),
  runSchedule: (id: number) => data<AuditRunResult>(api.post(`/briefings/schedules/${id}/run`, undefined, { timeout: 120_000 })),
};

export const integrationsApi = {
  list: () => data<IntegrationsResponse>(api.get('/integrations/')),
  save: (kind: string, values: Record<string, string>) => data<Integration>(api.put(`/integrations/${kind}`, { values })),
  disconnect: (kind: string) => data<Integration>(api.delete(`/integrations/${kind}`)),
  test: (kind: string) => data<IntegrationTestResult>(api.post(`/integrations/${kind}/test`, undefined, { timeout: 60_000 })),
  setDefaultTracker: (tracker: TrackerKind) => data<IntegrationsResponse>(api.put('/integrations/default-tracker', { default_tracker: tracker })),
};

export const settingsApi = {
  ai: () => data<AiSettings>(api.get('/settings/ai')),
  updateAi: (payload: { gemini_api_key?: string; openai_api_key?: string; preferred_provider?: LlmProvider | null }) =>
    data<AiSettings>(api.put('/settings/ai', payload)),
  testKey: (provider: LlmProvider, apiKey: string) =>
    data<{ valid: boolean; message: string }>(api.post('/settings/ai/test', { provider, api_key: apiKey })),
  system: () => data<SystemStatus>(api.get('/settings/system')),
};
