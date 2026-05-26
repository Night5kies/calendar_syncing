'use client';

import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { getPublicShare } from '../../../lib/api';

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
          setError(loadError instanceof Error ? loadError.message : 'Unable to load this link.');
        }
      }
    }
    go();
    return () => {
      cancelled = true;
    };
  }, [router, token]);

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Attendee view</p>
        <h1>{error ? 'Unable to load link' : 'Redirecting...'}</h1>
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </main>
  );
}
