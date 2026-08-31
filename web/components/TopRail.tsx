'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useAuth } from './AuthProvider';

/**
 * Attendee pages carry the mark only. Someone who arrived from a group chat is
 * here to tap a time, not to browse a product.
 */
function isAttendeePath(pathname: string | null): boolean {
  if (!pathname) return false;
  return pathname.startsWith('/respond/') || /^\/events\/[^/]+\/respond/.test(pathname);
}

export function TopRail() {
  const pathname = usePathname();
  const { authEnabled, session, email, signOut } = useAuth();
  const bare = isAttendeePath(pathname);

  return (
    <header className="rail">
      <div className="wrap rail-inner">
        <Link className="mark" href="/">
          SYZY
        </Link>

        {bare ? (
          <span className="muted">Respond in your browser</span>
        ) : (
          <nav className="rail-nav" aria-label="Main">
            <Link
              className="rail-link"
              href="/create"
              data-current={pathname === '/create' ? 'true' : 'false'}
            >
              New request
            </Link>
            <Link
              className="rail-link"
              href="/settings/availability"
              data-current={pathname?.startsWith('/settings') ? 'true' : 'false'}
            >
              Availability
            </Link>
            {authEnabled && session ? (
              <>
                <span className="rail-who">{email}</span>
                <button type="button" className="btn btn-text btn-small" onClick={() => void signOut()}>
                  Sign out
                </button>
              </>
            ) : null}
          </nav>
        )}
      </div>
    </header>
  );
}
