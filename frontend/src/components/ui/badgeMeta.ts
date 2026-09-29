import type { Priority, TaskStatus, Verdict } from '../../types/api';

export const PRIORITY_META: Record<Priority, { label: string; className: string; description: string }> = {
  1: { label: 'P1', className: 'border-rose-200 bg-rose-50 text-rose-800', description: 'Priority 1: highest, do first.' },
  2: { label: 'P2', className: 'border-amber-200 bg-amber-50 text-amber-800', description: 'Priority 2: normal.' },
  3: { label: 'P3', className: 'border-line bg-canvas text-muted', description: 'Priority 3: lowest, can slip.' },
};

export const PRIORITIES: Priority[] = [1, 2, 3];

export const VERDICT_META: Record<Verdict, { label: string; className: string; description: string }> = {
  VERIFIED_DONE: { label: 'Verified done', className: 'border-emerald-200 bg-emerald-50 text-emerald-800', description: 'GitHub confirms it was merged or closed as completed.' },
  CLAIMED_UNVERIFIED: { label: 'Claimed, unverified', className: 'border-amber-200 bg-amber-50 text-amber-800', description: 'Someone reported it done, but GitHub does not confirm it.' },
  OVERDUE: { label: 'Overdue', className: 'border-rose-200 bg-rose-50 text-rose-800', description: 'Past its target date and not verified done.' },
  DUE_TODAY: { label: 'Due today', className: 'border-orange-200 bg-orange-50 text-orange-800', description: 'Due today and not verified done.' },
  BLOCKED: { label: 'Blocked', className: 'border-rose-200 bg-rose-50 text-rose-800', description: 'The owner reported a blocker.' },
  AT_RISK: { label: 'At risk', className: 'border-amber-200 bg-amber-50 text-amber-800', description: 'Due soon with no progress, or its GitHub item was closed without completion.' },
  ON_TRACK: { label: 'On track', className: 'border-blue-200 bg-blue-50 text-blue-800', description: 'Target date is still ahead.' },
  NO_DEADLINE: { label: 'No deadline', className: 'border-line bg-canvas text-muted', description: 'No target date was committed.' },
  CANCELLED: { label: 'Cancelled', className: 'border-line bg-canvas text-subtle', description: 'Cancelled.' },
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  OPEN: 'Open',
  IN_PROGRESS: 'In progress',
  IN_REVIEW: 'In review',
  BLOCKED: 'Blocked',
  DONE: 'Done',
  CANCELLED: 'Cancelled',
};
