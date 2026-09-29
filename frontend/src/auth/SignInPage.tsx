import { useState, type FormEvent } from 'react';
import { FlaskConical } from 'lucide-react';

import { useAuth } from './useAuth';
import { usePublicConfig } from '../api/queries';
import { Logo, Wordmark } from '../components/Logo';
import { Alert } from '../components/ui/Alert';
import { Button } from '../components/ui/Button';
import { TextField } from '../components/ui/Field';
import { errorMessage } from '../lib/api';

type Mode = 'signin' | 'signup';

export function SignInPage() {
  const { signIn, signUp, startDemo, notice } = useAuth();
  const { data: config } = usePublicConfig();
  const minPassword = config?.password_min_length ?? 10;

  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<'form' | 'demo' | null>(null);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setPending('form');
    try {
      if (mode === 'signin') await signIn(email.trim(), password);
      else await signUp(email.trim(), password, fullName.trim());
    } catch (err) {
      setError(errorMessage(err, mode === 'signin' ? 'Could not sign in.' : 'Could not create the account.'));
      setPending(null);
    }
  };

  const handleDemo = async () => {
    setError(null);
    setPending('demo');
    try {
      await startDemo();
    } catch (err) {
      setError(errorMessage(err, 'Could not start a demo workspace.'));
      setPending(null);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo size={40} />
          <Wordmark />
          <p className="text-sm text-muted">Turn meeting commitments into verified delivery.</p>
        </div>

        <div className="rounded-xl border border-line bg-white p-6 shadow-sm">
          <div role="tablist" aria-label="Account" className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-canvas p-1">
            {(['signin', 'signup'] as const).map((tab) => (
              <button
                key={tab}
                role="tab"
                type="button"
                aria-selected={mode === tab}
                onClick={() => switchMode(tab)}
                className={
                  mode === tab
                    ? 'h-9 rounded-md bg-white text-sm font-semibold text-ink shadow-sm'
                    : 'h-9 rounded-md text-sm font-medium text-muted hover:text-ink'
                }
              >
                {tab === 'signin' ? 'Sign in' : 'Create account'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {notice && !error && <Alert tone="info">{notice}</Alert>}
            {error && <Alert tone="error">{error}</Alert>}

            {mode === 'signup' && (
              <TextField
                label="Full name"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                maxLength={120}
              />
            )}
            <TextField
              label="Work email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <TextField
              label="Password"
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              hint={mode === 'signup' ? `At least ${minPassword} characters, including a letter and a number.` : undefined}
              required
              minLength={mode === 'signup' ? minPassword : undefined}
              maxLength={64}
            />
            <Button type="submit" className="w-full" loading={pending === 'form'} disabled={pending !== null}>
              {mode === 'signin' ? 'Sign in' : 'Create account'}
            </Button>
          </form>

          {config?.demo_mode && (
            <div className="mt-5 border-t border-line pt-5">
              <Button
                variant="secondary"
                className="w-full"
                icon={<FlaskConical size={15} aria-hidden="true" />}
                loading={pending === 'demo'}
                disabled={pending !== null}
                onClick={handleDemo}
              >
                Try a private demo workspace
              </Button>
              <p className="mt-2 text-center text-xs text-muted">Creates an isolated, throwaway workspace. No account needed.</p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
