'use client';

import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { getPublicShare, submitPublicResponse, type PublicSharePayload } from '../../../lib/api';
import { formatRange } from '../../../lib/types';

const GUEST_KEY_STORAGE = 'syzy-web-guest-key';

function getGuestKey() {
  if (typeof window === 'undefined') {
    return 'server-guest';
  }
  const existing = localStorage.getItem(GUEST_KEY_STORAGE);
  if (existing) {
    return existing;
  }
  const next = `guest-${Math.random().toString(36).slice(2, 10)}`;
  localStorage.setItem(GUEST_KEY_STORAGE, next);
  return next;
}

export default function RespondPage() {
  const params = useParams<{ id: string }>();
  const token = Array.isArray(params.id) ? params.id[0] : params.id;
  const [share, setShare] = useState<PublicSharePayload | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submittingChoice, setSubmittingChoice] = useState<'picked' | 'maybe' | 'declined' | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const payload = await getPublicShare(token);
        if (!cancelled) {
          setShare(payload);
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
  }, [token]);

  const request = share?.request;
  const guestKey = useMemo(() => getGuestKey(), []);

  async function submit(choice: 'picked' | 'maybe' | 'declined') {
    if (!request) {
      return;
    }
    if (!displayName.trim()) {
      setError('Enter your name before submitting.');
      return;
    }
    if (choice === 'picked' && !selectedProposalId) {
      setError('Choose a time option first.');
      return;
    }

    setError(null);
    setSuccess(null);
    setSubmittingChoice(choice);

    try {
      await submitPublicResponse(token, {
        display_name: displayName.trim(),
        guest_key: guestKey,
        proposal_id: choice === 'declined' ? null : selectedProposalId,
        choice,
        comment: comment.trim() || undefined,
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
      });
      setSuccess('Response submitted.');
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to submit response.');
    } finally {
      setSubmittingChoice(null);
    }
  }

  if (error && !request) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Attendee view</p>
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
          <p className="eyebrow">Attendee view</p>
          <h1>Loading request…</h1>
        </div>
      </main>
    );
  }

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Attendee view</p>
        <h1>{request.title}</h1>
        <p className="lede">
          Respond from the browser. No account or app install is required.
        </p>
      </div>

      <form className="stack-form" onSubmit={(event) => event.preventDefault()}>
        <label className="field">
          <span>Your name</span>
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </label>

        <label className="field">
          <span>Email (optional)</span>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="email@example.com"
          />
        </label>

        <label className="field">
          <span>Phone (optional)</span>
          <input
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="555-222-0101"
          />
        </label>

        <section className="panel">
          <p className="section-label">Choose an option</p>
          <div className="option-list">
            {request.proposals.map((proposal, index) => (
              <button
                className={
                  selectedProposalId === proposal.id
                    ? 'option-card option-card-active'
                    : 'option-card'
                }
                key={proposal.id}
                onClick={() => setSelectedProposalId(proposal.id)}
                type="button"
              >
                <div className="option-copy">
                  <strong>Option {index + 1}</strong>
                  <p>{formatRange(proposal.start_at, proposal.end_at, request.timezone)}</p>
                </div>
              </button>
            ))}
          </div>
        </section>

        <label className="field">
          <span>Comment (optional)</span>
          <textarea
            rows={3}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="After 7 works best for me"
          />
        </label>

        <div className="button-group">
          <button
            className="button button-primary"
            disabled={submittingChoice !== null}
            onClick={() => submit('picked')}
            type="button"
          >
            {submittingChoice === 'picked' ? 'Submitting…' : 'Pick selected time'}
          </button>
          <button
            className="button button-secondary"
            disabled={submittingChoice !== null}
            onClick={() => submit('maybe')}
            type="button"
          >
            {submittingChoice === 'maybe' ? 'Submitting…' : 'Maybe'}
          </button>
          <button
            className="button button-secondary"
            disabled={submittingChoice !== null}
            onClick={() => submit('declined')}
            type="button"
          >
            {submittingChoice === 'declined' ? 'Submitting…' : 'Can’t make it'}
          </button>
        </div>

        {error ? <p className="error-text">{error}</p> : null}
        {success ? <p className="success-text">{success}</p> : null}
      </form>
    </main>
  );
}
