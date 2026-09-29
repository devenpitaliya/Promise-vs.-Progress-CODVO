import { Component, useState, type ErrorInfo, type ReactNode } from 'react';

import { AppShell } from './AppShell';
import { useRoute } from './useRoute';
import { useAuth } from '../auth/useAuth';
import { SignInPage } from '../auth/SignInPage';
import { Button } from '../components/ui/Button';
import { LoadingState } from '../components/ui/States';
import { CommitmentDrawer } from '../features/commitments/CommitmentDrawer';
import { CommitmentsPage } from '../features/commitments/CommitmentsPage';
import { MeetingsPage } from '../features/meetings/MeetingsPage';
import { ReconciliationPage } from '../features/reconciliation/ReconciliationPage';
import { SettingsPage } from '../features/settings/SettingsPage';

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto mt-24 max-w-md rounded-xl border border-line bg-white p-8 text-center">
        <h1 className="text-lg font-semibold text-ink">Something went wrong</h1>
        <p className="mt-1 text-sm text-muted">The page hit an unexpected error. Reloading usually fixes it.</p>
        <Button className="mt-5" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    );
  }
}

function Workspace() {
  const [route, navigate] = useRoute();
  const [openTaskId, setOpenTaskId] = useState<number | null>(null);

  return (
    <AppShell route={route} onNavigate={navigate}>
      <ErrorBoundary key={route}>
        {route === 'meetings' && <MeetingsPage onOpenTask={setOpenTaskId} onGoToCommitments={() => navigate('commitments')} />}
        {route === 'commitments' && <CommitmentsPage onOpenTask={setOpenTaskId} />}
        {route === 'reconciliation' && <ReconciliationPage onOpenTask={setOpenTaskId} />}
        {route === 'settings' && <SettingsPage />}
      </ErrorBoundary>
      <CommitmentDrawer taskId={openTaskId} onClose={() => setOpenTaskId(null)} />
    </AppShell>
  );
}

export function App() {
  const { status } = useAuth();
  if (status === 'loading') return <LoadingState label="Restoring your session…" />;
  if (status === 'anonymous') return <SignInPage />;
  return (
    <ErrorBoundary>
      <Workspace />
    </ErrorBoundary>
  );
}
