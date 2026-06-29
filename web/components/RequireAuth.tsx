'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { useAuth } from './AuthProvider';

/**
 * Gates organizer-only pages. When auth is disabled (no Supabase env), renders
 * children directly so local/dev keeps working against the backend dev-auth
 * fallback. When enabled, requires a signed-in session and redirects otherwise.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { authEnabled, loading, session, email, signOut } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (authEnabled && !loading && !session) {
      router.replace('/signin');
    }
  }, [authEnabled, loading, session, router]);

  if (!authEnabled) return <>{children}</>;

  if (loading) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">SYZY</p>
          <h1>Loading…</h1>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">SYZY</p>
          <h1>Sign in required</h1>
          <p>
            <Link className="inline-link" href="/signin">
              Go to sign in
            </Link>
          </p>
        </div>
      </main>
    );
  }

  return (
    <>
      <div className="auth-bar">
        <span className="auth-bar-email">{email}</span>
        <button type="button" className="inline-link" onClick={() => void signOut()}>
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}
