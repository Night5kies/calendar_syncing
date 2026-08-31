'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { useAuth } from './AuthProvider';

/**
 * Gates organizer-only pages. When auth is disabled (no Supabase env), renders
 * children directly so local/dev keeps working against the backend dev-auth
 * fallback. When enabled, requires a signed-in session and redirects otherwise.
 * The signed-in identity and sign-out live in the top rail, not here.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { authEnabled, loading, session } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (authEnabled && !loading && !session) {
      router.replace('/signin');
    }
  }, [authEnabled, loading, session, router]);

  if (!authEnabled) return <>{children}</>;

  if (loading) {
    return (
      <main className="wrap-narrow page" aria-busy="true">
        <div className="head">
          <div className="skel" style={{ height: '2.5rem', width: '55%' }} />
          <div className="skel" style={{ height: '1rem', width: '35%' }} />
        </div>
        <span className="sr-only">Checking your session</span>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="wrap-narrow page">
        <div className="head">
          <h1 className="title-page">Sign in to keep going</h1>
          <p className="lede">Organizer pages need a session. Attendees never do.</p>
          <p>
            <Link href="/signin">Go to sign in</Link>
          </p>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
