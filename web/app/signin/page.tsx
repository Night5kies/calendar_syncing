'use client';

import Link from 'next/link';
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
      setError(err instanceof Error ? err.message : 'That link didn’t send. Try again.');
    }
  }

  if (!authEnabled) {
    return (
      <main className="wrap-narrow page">
        <div className="head reveal">
          <h1 className="title-page">Auth is not configured</h1>
          <p className="lede">
            This deployment runs without Supabase, so organizer pages are open and there is nothing
            to sign in to.
          </p>
          <p>
            <Link href="/create">Go make a request</Link>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="wrap-narrow page">
      <div className="head reveal">
        <h1 className="title-page">Sign in</h1>
        <p className="lede">
          Organizers sign in with a link we email you. No password to remember.
        </p>
      </div>

      {status === 'sent' ? (
        <section className="card reveal" style={{ ['--i' as string]: 1 }}>
          <h2 className="title-card">Check your inbox</h2>
          <p className="muted">
            We sent a sign-in link to <strong>{email}</strong>. Open it on this device.
          </p>
          <div className="row">
            <button className="btn btn-text btn-small" type="button" onClick={() => setStatus('idle')}>
              Use a different email
            </button>
          </div>
        </section>
      ) : (
        <form className="card reveal" style={{ ['--i' as string]: 1 }} onSubmit={onSubmit}>
          <label className="field">
            <span className="field-label">Email</span>
            <input
              className="input"
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </label>
          <button type="submit" className="btn btn-wide" disabled={status === 'sending'}>
            {status === 'sending' ? 'Sending…' : 'Email me a sign-in link'}
          </button>
          {error ? (
            <p className="note" data-tone="bad" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      )}
    </main>
  );
}
