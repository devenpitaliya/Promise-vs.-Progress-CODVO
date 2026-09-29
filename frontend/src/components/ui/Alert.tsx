import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import clsx from 'clsx';

type Tone = 'info' | 'success' | 'warning' | 'error';

const STYLES: Record<Tone, { box: string; Icon: typeof Info }> = {
  info: { box: 'border-blue-200 bg-blue-50 text-blue-900', Icon: Info },
  success: { box: 'border-emerald-200 bg-emerald-50 text-emerald-900', Icon: CheckCircle2 },
  warning: { box: 'border-amber-200 bg-amber-50 text-amber-900', Icon: AlertTriangle },
  error: { box: 'border-rose-200 bg-rose-50 text-rose-900', Icon: XCircle },
};

export function Alert({ tone = 'info', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  const { box, Icon } = STYLES[tone];
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={clsx('flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm', box, className)}
    >
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
