import { useEffect, useRef, useState, type ReactNode } from 'react';
import clsx from 'clsx';
import { CalendarDays, ChevronDown, FlaskConical, LayoutList, LogOut, RefreshCcw, Settings, Sparkles } from 'lucide-react';

import type { Route } from './useRoute';
import { useAiSettings, useMeetings, useSystemStatus } from '../api/queries';
import { useAuth } from '../auth/useAuth';
import { Logo, Wordmark } from '../components/Logo';
import { initials } from '../lib/format';

const NAV: { route: Route; label: string; Icon: typeof CalendarDays }[] = [
  { route: 'meetings', label: 'Meetings', Icon: CalendarDays },
  { route: 'commitments', label: 'Commitments', Icon: LayoutList },
  { route: 'reconciliation', label: 'Reconciliation', Icon: RefreshCcw },
  { route: 'settings', label: 'Settings', Icon: Settings },
];

function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-xs font-bold text-white">
          {initials(user?.full_name || user?.email)}
        </span>
        <ChevronDown size={14} className="text-muted" aria-hidden="true" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-60 rounded-lg border border-line bg-white py-1 shadow-lg">
          <div className="border-b border-line px-3 py-2">
            <div className="truncate text-sm font-semibold text-ink">{user?.full_name}</div>
            <div className="truncate text-xs text-muted">{user?.is_demo ? 'Demo workspace' : user?.email}</div>
          </div>
          <button
            role="menuitem"
            type="button"
            onClick={signOut}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-rose-700 hover:bg-rose-50"
          >
            <LogOut size={14} aria-hidden="true" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function ModePills({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { data: ai } = useAiSettings();
  const { data: system } = useSystemStatus();
  const aiLabel = ai ? (ai.active_provider === 'rules' ? 'Rule-based extraction' : `AI: ${ai.active_provider === 'gemini' ? 'Gemini' : 'OpenAI'}`) : null;

  return (
    <div className="hidden items-center gap-2 md:flex">
      {aiLabel && (
        <button
          type="button"
          onClick={onOpenSettings}
          className={clsx(
            'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold',
            ai?.active_provider === 'rules' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800',
          )}
          title="Change in Settings"
        >
          <Sparkles size={12} aria-hidden="true" /> {aiLabel}
        </button>
      )}
      {system?.github_mode === 'simulated' && (
        <span
          className="inline-flex h-8 items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3 text-xs font-semibold text-violet-800"
          title="No GitHub token is configured on the server, so GitHub state is simulated."
        >
          <FlaskConical size={12} aria-hidden="true" /> GitHub simulated
        </span>
      )}
    </div>
  );
}

export function AppShell({ route, onNavigate, children }: { route: Route; onNavigate: (r: Route) => void; children: ReactNode }) {
  const { data: meetings } = useMeetings();
  const pending = meetings?.reduce((sum, m) => sum + m.pending_count, 0) ?? 0;

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-white px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <Logo />
          <Wordmark />
        </div>
        <div className="flex items-center gap-3">
          <ModePills onOpenSettings={() => onNavigate('settings')} />
          <UserMenu />
        </div>
      </header>

      <div className="flex flex-1">
        <nav aria-label="Main" className="w-16 shrink-0 border-r border-line bg-white p-2 lg:w-56 lg:p-3">
          <ul className="space-y-1">
            {NAV.map(({ route: target, label, Icon }) => {
              const active = route === target;
              return (
                <li key={target}>
                  <a
                    href={`/${target}`}
                    aria-current={active ? 'page' : undefined}
                    title={label}
                    onClick={(e) => {
                      e.preventDefault();
                      onNavigate(target);
                    }}
                    className={clsx(
                      'flex h-10 items-center justify-center gap-3 rounded-lg px-3 text-sm font-medium lg:justify-start',
                      active ? 'bg-brand-soft text-brand' : 'text-body hover:bg-canvas hover:text-ink',
                    )}
                  >
                    <Icon size={18} aria-hidden="true" />
                    <span className="hidden flex-1 lg:inline">{label}</span>
                    {target === 'meetings' && pending > 0 && (
                      <span className="hidden rounded-full bg-amber-100 px-1.5 text-[11px] font-bold text-amber-800 lg:inline" title={`${pending} commitments need review`}>
                        {pending}
                      </span>
                    )}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>

        <main id="main" className="min-w-0 flex-1 px-4 py-6 sm:px-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
