// Mirrors backend/app/schemas. Keep in sync when the API changes.

export type TargetSystem = 'github_issue' | 'github_pr' | 'jira';
export type SpeechStatus = 'PROPOSED' | 'COMPLETED_IN_SPEECH' | 'BLOCKED';
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type TaskStatus = 'OPEN' | 'IN_PROGRESS' | 'IN_REVIEW' | 'BLOCKED' | 'DONE' | 'CANCELLED';
export type SyncStatus = 'NOT_SYNCED' | 'SYNCED' | 'FAILED';
export type VerificationStatus =
  | 'NOT_CHECKED'
  | 'VERIFIED_DONE'
  | 'OPEN'
  | 'CLOSED_NOT_COMPLETED'
  | 'CLOSED_FROM_APP'
  | 'NOT_TRACKABLE'
  | 'CHECK_FAILED';
export type Verdict =
  | 'VERIFIED_DONE'
  | 'CLAIMED_UNVERIFIED'
  | 'OVERDUE'
  | 'DUE_TODAY'
  | 'BLOCKED'
  | 'AT_RISK'
  | 'ON_TRACK'
  | 'NO_DEADLINE'
  | 'CANCELLED';
/** 1 = highest, 3 = lowest. */
export type Priority = 1 | 2 | 3;
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type GithubMode = 'live' | 'simulated';
export type LlmSource = 'gemini' | 'openai' | 'rules';

export interface PublicConfig {
  app_name: string;
  demo_mode: boolean;
  password_min_length: number;
  max_transcript_chars: number;
  max_participants: number;
}

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_demo: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Participant {
  name: string;
  role?: string | null;
}

export interface Task {
  id: number;
  meeting_id: number;
  meeting_title: string | null;
  assignee: string;
  description: string;
  source_quote: string | null;
  target_date: string | null;
  priority: Priority;
  speech_status: SpeechStatus;
  target_system: TargetSystem;
  repository: string | null;
  external_ref: string | null;
  approval_status: ApprovalStatus;
  status: TaskStatus;
  sync_status: SyncStatus;
  sync_error: string | null;
  is_simulated: boolean;
  github_url: string | null;
  github_issue_number: number | null;
  github_pr_number: number | null;
  external_key: string | null;
  /** What happened in GitHub after this edit (two-way sync); only in the response to that edit. */
  tracker_update?: string | null;
  verification_status: VerificationStatus;
  github_state: string | null;
  verification_note: string | null;
  last_checked_at: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskUpdate {
  assignee?: string;
  description?: string;
  target_date?: string | null;
  priority?: Priority;
  target_system?: TargetSystem;
  repository?: string | null;
  external_ref?: string | null;
  status?: TaskStatus;
}

export interface TaskCreate {
  meeting_id: number;
  assignee: string;
  description: string;
  target_date?: string | null;
  priority?: Priority;
  target_system?: TargetSystem;
  repository?: string | null;
  external_ref?: string | null;
}

export interface RetryFailedResult {
  retried: number;
  synced: number;
  failures: { task_id: number; error: string }[];
}

export interface SimulatedSyncResult {
  moved: number;
  failures: { task_id: number; error: string }[];
}

export interface ReviewResult {
  approved: Task[];
  rejected_ids: number[];
  sync_failures: { task_id: number; error: string }[];
}

export interface Meeting {
  id: number;
  title: string;
  meeting_type: string | null;
  meeting_date: string;
  meeting_time: string | null;
  participants: Participant[];
  transcript: string;
  summary: string | null;
  extraction_source: LlmSource;
  trace_url: string | null;
  created_at: string;
  tasks: Task[];
}

export interface MeetingListItem {
  id: number;
  title: string;
  meeting_type: string | null;
  meeting_date: string;
  meeting_time: string | null;
  participants: Participant[];
  created_at: string;
  task_count: number;
  pending_count: number;
  approved_count: number;
  verified_count: number;
}

export interface MeetingCreate {
  title: string;
  meeting_type?: string | null;
  meeting_date?: string | null;
  meeting_time?: string | null;
  participants: Participant[];
  transcript: string;
}

/** A Teams/Zoom .vtt or .srt file converted to "Name: text" lines (POST /meetings/transcript/convert). */
export interface ConvertedTranscript {
  transcript: string;
  format: 'vtt' | 'srt' | 'text';
  speakers: string[];
  lines: number;
  too_long: boolean;
}

export interface SampleTranscript {
  title: string;
  description: string;
  meeting_type: string;
  participants: Participant[];
  transcript: string;
}

export interface ReconciliationItem {
  task_id: number;
  sync_status: SyncStatus;
  sync_error: string | null;
  external_key: string | null;
  target_system: TargetSystem;
  meeting_id: number;
  meeting_title: string | null;
  assignee: string;
  description: string;
  repository: string | null;
  external_ref: string | null;
  github_url: string | null;
  is_simulated: boolean;
  target_date: string | null;
  priority: Priority;
  status: TaskStatus;
  verification_status: VerificationStatus;
  github_state: string | null;
  last_checked_at: string | null;
  verdict: Verdict;
  days_overdue: number | null;
  days_remaining: number | null;
  risk_score: number;
  risk_level: RiskLevel;
  risk_reason: string;
  note: string;
}

export interface ReconciliationReport {
  generated_at: string;
  today: string;
  timezone: string;
  github_mode: GithubMode;
  meeting_id: number | null;
  total: number;
  counts: Record<Verdict, number>;
  completion_rate: number;
  items: ReconciliationItem[];
}

export interface BriefingPreview {
  subject: string;
  executive_summary: string;
  agenda: string[];
  html: string;
  counts: Record<Verdict, number>;
  completion_rate: number;
  generated_by: LlmSource;
  github_mode: GithubMode;
}

export type EmailStatus = 'sent' | 'failed' | 'not_configured';

export interface EmailLog {
  id: number;
  recipient_email: string;
  subject: string;
  status: EmailStatus;
  error: string | null;
  meeting_id: number | null;
  audit_id: number | null;
  created_at: string;
}

export type ScheduleType = 'single' | 'recurring';
export type ScheduleStatus = 'active' | 'completed' | 'cancelled' | 'failed';

export interface ScheduledAudit {
  id: number;
  recipient_email: string | null;
  post_to_slack: boolean;
  schedule_type: ScheduleType;
  timezone: string;
  run_at: string | null;
  start_date: string | null;
  end_date: string | null;
  daily_time: string | null;
  meeting_id: number | null;
  custom_instructions: string | null;
  status: ScheduleStatus;
  runs_count: number;
  last_run_at: string | null;
  last_error: string | null;
  next_run_at: string | null;
  created_at: string;
}

export interface ScheduleAuditRequest {
  recipient_email?: string;
  post_to_slack?: boolean;
  schedule_type: ScheduleType;
  timezone: string;
  run_at?: string;
  start_date?: string;
  end_date?: string;
  daily_time?: string;
  meeting_id?: number;
  custom_instructions?: string;
}

export type LlmProvider = 'gemini' | 'openai';

export interface AiSettings {
  gemini_key_masked: string | null;
  openai_key_masked: string | null;
  preferred_provider: LlmProvider | null;
  server_gemini_available: boolean;
  server_openai_available: boolean;
  active_provider: LlmSource;
  gemini_model: string;
  openai_model: string;
}

export interface SystemStatus {
  github_mode: GithubMode;
  smtp_configured: boolean;
  demo_mode: boolean;
  scheduler_running: boolean;
  app_timezone: string;
  jira_mode: GithubMode;
  slack_connected: boolean;
  default_tracker: TrackerKind;
  integrations_available: string[];
  tracing_enabled: boolean;
  tracing_url: string | null;
  tracing_off_reason: string | null;
}

export type TrackerKind = 'github' | 'jira';

export interface IntegrationField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  placeholder: string;
  help: string;
}

/** One external tool in Settings > Integrations (GET /integrations). */
export interface Integration {
  kind: string;
  label: string;
  category: 'tracker' | 'notifier';
  /** false = not enabled on this server yet: shown as "Coming soon". */
  available: boolean;
  fields: IntegrationField[];
  source: 'user' | 'server' | 'none';
  mode: GithubMode;
  has_user_connection: boolean;
  config: Record<string, string>;
  secrets_masked: Record<string, string | null>;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
}

export interface IntegrationsResponse {
  integrations: Integration[];
  default_tracker: TrackerKind;
}

export interface IntegrationTestResult {
  ok: boolean;
  message: string;
  tested_at: string;
}

export interface SlackPostResult {
  ok: boolean;
  message: string;
}

export interface AuditRunResult {
  email: EmailLog | null;
  slack_ok: boolean | null;
  slack_message: string | null;
}
