'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import {
  getEventResponseContext,
  submitEventResponse,
  type EventRespondContext,
} from '../../../../lib/api';
import { detectBrowserTimezone, formatRange } from '../../../../lib/types';

type Choice = 'picked' | 'maybe' | 'declined';

function toCalendarStamp(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}` +
    `T${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}Z`
  );
}

function buildGoogleCalendarUrl(payload: {
  title: string;
  startIso: string;
  endIso: string;
  details: string;
  location: string;
}): string {
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: payload.title,
    dates: `${toCalendarStamp(payload.startIso)}/${toCalendarStamp(payload.endIso)}`,
    details: payload.details,
    location: payload.location,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function buildOutlookCalendarUrl(payload: {
  title: string;
  startIso: string;
  endIso: string;
  details: string;
  location: string;
}): string {
  const params = new URLSearchParams({
    path: '/calendar/action/compose',
    rru: 'addevent',
    subject: payload.title,
    startdt: payload.startIso,
    enddt: payload.endIso,
    body: payload.details,
    location: payload.location,
  });
  return `https://outlook.live.com/calendar/0/deeplink/compose?${params.toString()}`;
}

export default function EventRespondPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const eventId = Array.isArray(params.id) ? params.id[0] : params.id;
  const inviteToken = searchParams.get('token');

  const [context, setContext] = useState<EventRespondContext | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [comment, setComment] = useState('');
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [checkEmail, setCheckEmail] = useState<string | null>(null);
  const [submittingChoice, setSubmittingChoice] = useState<Choice | null>(null);
  const [submittedChoice, setSubmittedChoice] = useState<Choice | null>(null);
  const [submittedProposalLabel, setSubmittedProposalLabel] = useState<string | null>(null);

  const browserTimezone = useMemo(() => detectBrowserTimezone(), []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const payload = await getEventResponseContext(eventId, inviteToken);
        if (cancelled) return;
        setContext(payload);
        if (payload.invited_as) {
          setDisplayName(payload.invited_as.display_name ?? '');
          setEmail(payload.invited_as.email ?? '');
          const existing = payload.invited_as.current_response;
          if (existing) {
            setSelectedProposalId(existing.proposal_id);
            setComment(existing.comment ?? '');
            setSubmittedChoice(existing.choice);
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Unable to load event.');
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [eventId, inviteToken]);

  const event = context?.event;
  const confirmedEvent = context?.confirmed_event ?? null;
  const invitedAs = context?.invited_as;
  const isTokenMode = Boolean(invitedAs);
  const isConfirmed = event?.status === 'confirmed' && confirmedEvent !== null;
  const organizerTimezone = event?.timezone ?? 'UTC';
  const showsLocalTime = browserTimezone !== organizerTimezone;

  async function submit(choice: Choice) {
    if (!event) return;

    if (!isTokenMode) {
      if (!displayName.trim()) {
        setError('Enter your name before submitting.');
        return;
      }
      if (!email.trim()) {
        setError('Enter the email you were invited with — or any email if you are responding via the general link.');
        return;
      }
    }
    if (choice === 'picked' && !selectedProposalId) {
      setError('Choose a time option first.');
      return;
    }

    setError(null);
    setCheckEmail(null);
    setSuccess(null);
    setSubmittingChoice(choice);

    try {
      const result = await submitEventResponse(eventId, {
        display_name: displayName.trim() || undefined,
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        proposal_id: choice === 'declined' ? null : selectedProposalId,
        choice,
        comment: comment.trim() || undefined,
        invite_token: inviteToken ?? undefined,
      });

      if ('status' in result && result.status === 'check_email') {
        setCheckEmail(result.message);
        return;
      }

      const proposalLabel =
        choice === 'declined' || !selectedProposalId
          ? null
          : event.proposals.find((proposal) => proposal.id === selectedProposalId);
      setSubmittedChoice(choice);
      setSubmittedProposalLabel(
        proposalLabel ? formatRange(proposalLabel.start_at, proposalLabel.end_at, browserTimezone) : null,
      );
      setSuccess(
        choice === 'picked'
          ? 'You are in. The organizer can now see your selected time.'
          : choice === 'maybe'
            ? 'Marked as maybe. You can still update your response from this link.'
            : "Marked as unavailable. You can still update your response from this link.",
      );
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to submit response.');
    } finally {
      setSubmittingChoice(null);
    }
  }

  if (error && !event) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Attendee view</p>
          <h1>Unable to load event</h1>
          <p className="error-text">{error}</p>
        </div>
      </main>
    );
  }

  if (!event) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Attendee view</p>
          <h1>Loading event...</h1>
        </div>
      </main>
    );
  }

  if (isConfirmed && confirmedEvent) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Attendee view</p>
          <h1>{event.title}</h1>
          <p className="lede">This is confirmed. Save the time below to your calendar.</p>
        </div>

        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-label">Confirmed</p>
              <h2>
                {confirmedEvent.start_at && confirmedEvent.end_at
                  ? formatRange(confirmedEvent.start_at, confirmedEvent.end_at, browserTimezone)
                  : 'Time pending'}
              </h2>
            </div>
            <span className="status-pill status-confirmed">confirmed</span>
          </div>
          {showsLocalTime ? (
            <p className="helper-copy">
              Shown in your local timezone ({browserTimezone}). Organizer scheduled in {organizerTimezone}.
            </p>
          ) : (
            <p className="helper-copy">Shown in {browserTimezone}.</p>
          )}
          <div className="flat-list">
            {confirmedEvent.location ? (
              <div className="stat-row">
                <span>Location</span>
                <strong>{confirmedEvent.location}</strong>
              </div>
            ) : null}
            {confirmedEvent.video_link ? (
              <div className="stat-row">
                <span>Video link</span>
                <strong>
                  <a href={confirmedEvent.video_link} rel="noreferrer" target="_blank">
                    {confirmedEvent.video_link}
                  </a>
                </strong>
              </div>
            ) : null}
            {confirmedEvent.notes ? (
              <div className="stat-row">
                <span>Notes</span>
                <strong>{confirmedEvent.notes}</strong>
              </div>
            ) : null}
          </div>
          <div className="button-group">
            {confirmedEvent.start_at && confirmedEvent.end_at ? (
              <>
                <a
                  className="button button-primary"
                  href={buildGoogleCalendarUrl({
                    title: event.title,
                    startIso: confirmedEvent.start_at,
                    endIso: confirmedEvent.end_at,
                    details: confirmedEvent.notes ?? '',
                    location: confirmedEvent.location ?? confirmedEvent.video_link ?? '',
                  })}
                  rel="noreferrer"
                  target="_blank"
                >
                  Add to Google Calendar
                </a>
                <a
                  className="button button-secondary"
                  href={buildOutlookCalendarUrl({
                    title: event.title,
                    startIso: confirmedEvent.start_at,
                    endIso: confirmedEvent.end_at,
                    details: confirmedEvent.notes ?? '',
                    location: confirmedEvent.location ?? confirmedEvent.video_link ?? '',
                  })}
                  rel="noreferrer"
                  target="_blank"
                >
                  Add to Outlook
                </a>
              </>
            ) : null}
            {confirmedEvent.artifact_url ? (
              <a
                className="button button-secondary"
                href={confirmedEvent.artifact_url}
                rel="noreferrer"
                target="_blank"
              >
                Apple Calendar (.ics)
              </a>
            ) : null}
          </div>
          {!confirmedEvent.artifact_url ? (
            <p className="helper-copy">
              ICS file isn’t ready yet — the Google/Outlook buttons still work.
            </p>
          ) : null}
        </section>
      </main>
    );
  }

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Attendee view</p>
        <h1>{event.title}</h1>
        {isTokenMode ? (
          <p className="lede">
            Responding as <strong>{invitedAs?.display_name || invitedAs?.email || 'invited guest'}</strong>.
          </p>
        ) : (
          <p className="lede">Respond from the browser. No account or app install is required.</p>
        )}
      </div>

      {checkEmail ? (
        <section className="panel">
          <p className="section-label">Check your email</p>
          <h2>We sent you a private link</h2>
          <p className="helper-copy">{checkEmail}</p>
        </section>
      ) : null}

      {submittedChoice && !checkEmail ? (
        <section className="panel">
          <p className="section-label">Response saved</p>
          <h2>
            {submittedChoice === 'picked'
              ? 'You picked a time'
              : submittedChoice === 'maybe'
                ? 'You marked maybe'
                : "You can't make it"}
          </h2>
          <p className="helper-copy">
            {submittedProposalLabel ? `Submitted choice: ${submittedProposalLabel}. ` : ''}
            {success}
          </p>
        </section>
      ) : null}

      <form className="stack-form" onSubmit={(formEvent) => formEvent.preventDefault()}>
        <label className="field">
          <span>Your name</span>
          <input
            value={displayName}
            onChange={(formEvent) => setDisplayName(formEvent.target.value)}
            readOnly={isTokenMode && Boolean(invitedAs?.display_name)}
          />
        </label>

        <label className="field">
          <span>Email{isTokenMode ? ' (locked)' : ''}</span>
          <input
            value={email}
            onChange={(formEvent) => setEmail(formEvent.target.value)}
            placeholder="email@example.com"
            readOnly={isTokenMode}
          />
          {!isTokenMode ? (
            <span className="helper-copy">Use the email you were invited with, if you received an invite.</span>
          ) : null}
        </label>

        {!isTokenMode ? (
          <label className="field">
            <span>Phone (optional)</span>
            <input
              value={phone}
              onChange={(formEvent) => setPhone(formEvent.target.value)}
              placeholder="555-222-0101"
            />
          </label>
        ) : null}

        <section className="panel">
          <p className="section-label">Choose an option</p>
          <p className="helper-copy">
            {showsLocalTime
              ? `Times shown in your local timezone (${browserTimezone}). Organizer scheduled in ${organizerTimezone}.`
              : `Times shown in ${browserTimezone}.`}
          </p>
          <div className="option-list">
            {event.proposals.map((proposal, index) => (
              <button
                className={
                  selectedProposalId === proposal.id ? 'option-card option-card-active' : 'option-card'
                }
                key={proposal.id}
                onClick={() => setSelectedProposalId(proposal.id)}
                type="button"
              >
                <div className="option-copy">
                  <strong>Option {index + 1}</strong>
                  <p>{formatRange(proposal.start_at, proposal.end_at, browserTimezone)}</p>
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
            onChange={(formEvent) => setComment(formEvent.target.value)}
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
            {submittingChoice === 'picked' ? 'Submitting...' : 'Pick selected time'}
          </button>
          <button
            className="button button-secondary"
            disabled={submittingChoice !== null}
            onClick={() => submit('maybe')}
            type="button"
          >
            {submittingChoice === 'maybe' ? 'Submitting...' : 'Maybe'}
          </button>
          <button
            className="button button-secondary"
            disabled={submittingChoice !== null}
            onClick={() => submit('declined')}
            type="button"
          >
            {submittingChoice === 'declined' ? 'Submitting...' : "Can't make it"}
          </button>
        </div>

        {error ? <p className="error-text">{error}</p> : null}
      </form>
    </main>
  );
}
