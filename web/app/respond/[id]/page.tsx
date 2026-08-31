'use client';

import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { getPublicShare } from '../../../lib/api';

/** Older share links pointed at the token. Send those people to the event page. */
export default function LegacyRespondRedirect() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const token = Array.isArray(params.id) ? params.id[0] : params.id;
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function go() {
      try {
        const payload = await getPublicShare(token);
        if (cancelled) return;
        router.replace(`/events/${payload.request.id}/respond`);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Could not open this link.');
        }
      }
    }
    go();
    return () => {
      cancelled = true;
    };
  }, [router, token]);

  const expired = !!error && /expired/i.test(error);

  if (!error) {
    return (
      <main className="wrap-narrow page" aria-busy="true">
        <div className="head">
          <div className="skel" style={{ height: '2.5rem', width: '60%' }} />
          <div className="skel" style={{ height: '1rem', width: '40%' }} />
        </div>
        <span className="sr-only">Opening your invite</span>
      </main>
    );
  }

  return (
    <main className="wrap-narrow page">
      <div className="head">
        <h1 className="title-page">
          {expired ? 'This link has expired' : 'This link didn’t open'}
        </h1>
        <p className="lede">
          {expired ? 'Ask whoever sent it for a fresh one — it only takes them a tap.' : error}
        </p>
      </div>
    </main>
  );
}
