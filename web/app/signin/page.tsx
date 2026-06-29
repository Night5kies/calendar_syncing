'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { useAuth } from '../../components/AuthProvider';

export default function SignInPage() {
  const { authEnabled, session, signInWithEmail } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (session) router.replace('/create');
  }, [session, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('sending');
    setError(null);
    try {
      await signInWithEmail(email.trim());
      setStatus('sent');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Could not send sign-in link.');
    }
  }

  if (!authEnabled) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Organizer sign in</p>
          <h1>Auth is not configured</h1>
          <p>
            This deployment is running in dev mode without Supabase. Organizer
            endpoints use the local dev-auth fallback — no sign-in required.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Organizer sign in</p>
        <h1>Sign in to SYZY</h1>
        <p>We&apos;ll email you a magic link — no password needed.</p>
      </div>

      {status === 'sent' ? (
        <p className="success-text">
          Check your inbox at <strong>{email}</strong> for a sign-in link.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <button type="submit" className="button" disabled={status === 'sending'}>
            {status === 'sending' ? 'Sending…' : 'Send magic link'}
          </button>
          {error ? <p className="error-text">{error}</p> : null}
        </form>
      )}
    </main>
  );
}
