'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  finalizeRequest,
  getOrganizerRequest,
  type OrganizerRequestDetail,
} from '../../../lib/api';
import { formatRange } from '../../../lib/types';

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const requestId = Array.isArray(params.id) ? params.id[0] : params.id;
  const [request, setRequest] = useState<OrganizerRequestDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const next = await getOrganizerRequest(requestId);
        if (!cancelled) {
          setRequest(next);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Unable to load request.');
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  async function copySharePath() {
    if (!request?.share) {
      return;
    }
    const sharePath = `/respond/${request.share.token}`;
    await navigator.clipboard.writeText(sharePath);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  async function confirmOption(proposalId: string) {
    setLoadingProposalId(proposalId);
    try {
      await finalizeRequest(requestId, proposalId);
      const next = await getOrganizerRequest(requestId);
      setRequest(next);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : 'Unable to confirm option.');
    } finally {
      setLoadingProposalId(null);
    }
  }

  if (error) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Organizer view</p>
          <h1>Unable to load request</h1>
          <p className="error-text">{error}</p>
        </div>
      </main>
    );
  }

  if (!request) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Organizer view</p>
          <h1>Loading request…</h1>
        </div>
      </main>
    );
  }

  const sharePath = request.share ? `/respond/${request.share.token}` : null;

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Organizer view</p>
        <h1>{request.title}</h1>
        <p className="lede">
          {request.duration_min} min · {request.timezone}
          {request.event_type ? ` · ${request.event_type}` : ''}
        </p>
      </div>

      <section className="grid-two">
        <article className="panel">
          <p className="section-label">Participants</p>
          <div className="chip-wrap">
            {request.participants.map((participant) => (
              <span className="chip" key={participant.id}>
                {participant.display_name ?? participant.email ?? participant.phone ?? 'Guest'}
              </span>
            ))}
          </div>
          <p className="helper-copy">
            {request.progress.responded_count}/{request.progress.participant_count} responded ·{' '}
            {request.progress.outstanding_count} outstanding
          </p>
          {request.notes ? <p className="helper-copy">{request.notes}</p> : null}
        </article>

        <article className="panel">
          <p className="section-label">Share</p>
          {sharePath ? (
            <>
              <div className="share-row">
                <code>{sharePath}</code>
                <button className="button button-secondary" onClick={copySharePath} type="button">
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="button-group">
                <Link className="button button-primary" href={sharePath}>
                  Preview attendee page
                </Link>
              </div>
            </>
          ) : (
            <p className="helper-copy">No share link available yet.</p>
          )}
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="section-label">Manual poll</p>
            <h2>Proposed times</h2>
          </div>
          <span className={`status-pill status-${request.status}`}>{request.status}</span>
        </div>
        <div className="option-list">
          {request.proposals.map((proposal, index) => {
            const tally = request.tallies[proposal.id] ?? {
              picked: 0,
              maybe: 0,
              declined: 0,
            };

            return (
              <article className="option-card" key={proposal.id}>
                <div className="option-copy">
                  <strong>Option {index + 1}</strong>
                  <p>{formatRange(proposal.start_at, proposal.end_at, request.timezone)}</p>
                  <p className="helper-copy">
                    {tally.picked} picked · {tally.maybe} maybe
                  </p>
                </div>
                <button
                  className="button button-secondary"
                  disabled={loadingProposalId === proposal.id}
                  onClick={() => confirmOption(proposal.id)}
                  type="button"
                >
                  {loadingProposalId === proposal.id ? 'Confirming…' : 'Confirm winner'}
                </button>
              </article>
            );
          })}
        </div>
      </section>
    </main>
  );
}
