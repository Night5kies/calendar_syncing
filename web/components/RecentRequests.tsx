'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { listRecentRequests, type RecentRequest } from '../lib/recents';
import { relativeTime } from '../lib/time';

export function RecentRequests() {
  const [recents, setRecents] = useState<RecentRequest[] | null>(null);

  useEffect(() => {
    setRecents(listRecentRequests());
  }, []);

  if (!recents || recents.length === 0) return null;

  return (
    <>
      <hr className="hairline" />
      <section className="stack">
        <div className="row-between">
          <h2 className="title-card">Your requests</h2>
          <span className="muted">Saved on this device</span>
        </div>
        <ul className="people">
          {recents.map((entry) => (
            <li className="person" key={entry.id}>
              <span className="dot" data-tone={entry.status === 'confirmed' ? 'in' : 'waiting'} />
              <span className="person-name">
                <strong>{entry.title}</strong>
                <span>{relativeTime(entry.createdAt) ?? ''}</span>
              </span>
              <Link className="btn btn-quiet btn-small" href={`/request/${entry.id}`}>
                Open
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
