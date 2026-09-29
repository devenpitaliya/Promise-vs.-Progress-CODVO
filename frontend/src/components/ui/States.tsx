import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

import { Alert } from './Alert';
import { Button } from './Button';
import { errorMessage } from '../../lib/api';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-16 text-sm text-muted">
      <Loader2 size={16} className="animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Alert tone="error" className="my-6">
      <div className="flex items-center justify-between gap-4">
        <span>{errorMessage(error)}</span>
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </Alert>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-white px-6 py-12 text-center">
      {icon && <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-brand-soft text-brand">{icon}</div>}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
