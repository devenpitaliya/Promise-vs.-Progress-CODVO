import clsx from 'clsx';
import { FlaskConical } from 'lucide-react';

import { PRIORITY_META, VERDICT_META } from './badgeMeta';
import type { ApprovalStatus, Priority, Verdict, VerificationStatus } from '../../types/api';

const pill = 'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold';

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const meta = VERDICT_META[verdict];
  return (
    <span className={clsx(pill, meta.className)} title={meta.description}>
      {meta.label}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  const meta = PRIORITY_META[priority] ?? PRIORITY_META[2];
  return (
    <span className={clsx(pill, meta.className)} title={meta.description}>
      {meta.label}
    </span>
  );
}

const VERIFICATION_LABEL: Record<VerificationStatus, { label: string; className: string }> = {
  NOT_CHECKED: { label: 'Not checked', className: 'border-line bg-canvas text-muted' },
  VERIFIED_DONE: { label: 'Verified', className: 'border-emerald-200 bg-emerald-50 text-emerald-800' },
  OPEN: { label: 'Open in GitHub', className: 'border-blue-200 bg-blue-50 text-blue-800' },
  CLOSED_NOT_COMPLETED: { label: 'Closed, not completed', className: 'border-amber-200 bg-amber-50 text-amber-800' },
  CLOSED_FROM_APP: { label: 'Closed from app (claimed)', className: 'border-amber-200 bg-amber-50 text-amber-800' },
  NOT_TRACKABLE: { label: 'Not trackable', className: 'border-line bg-canvas text-muted' },
  CHECK_FAILED: { label: 'Check failed', className: 'border-rose-200 bg-rose-50 text-rose-800' },
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const meta = VERIFICATION_LABEL[status];
  return <span className={clsx(pill, meta.className)}>{meta.label}</span>;
}

const APPROVAL_LABEL: Record<ApprovalStatus, { label: string; className: string }> = {
  PENDING: { label: 'Needs review', className: 'border-amber-200 bg-amber-50 text-amber-800' },
  APPROVED: { label: 'Approved', className: 'border-emerald-200 bg-emerald-50 text-emerald-800' },
  REJECTED: { label: 'Rejected', className: 'border-line bg-canvas text-subtle' },
};

export function ApprovalBadge({ status }: { status: ApprovalStatus }) {
  const meta = APPROVAL_LABEL[status];
  return <span className={clsx(pill, meta.className)}>{meta.label}</span>;
}

export function SimulatedBadge() {
  return (
    <span className={clsx(pill, 'border-violet-200 bg-violet-50 text-violet-800')} title="GitHub simulation mode: no real repository is involved.">
      <FlaskConical size={11} aria-hidden="true" />
      Simulated
    </span>
  );
}
