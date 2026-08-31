'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import {
  getEventResponseContext,
  submitEventResponse,
  type EventRespondContext,
} from '../../../../lib/api';
import { Slot, SlotChoice } from '../../../../components/Slot';
import { browserTimezone, formatDuration, shapeSlot, zoneLabel } from '../../../../lib/time';

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

const ANSWER_COPY: Record<Choice, { heading: string; detail: string }> = {
  picked: {
    heading: 'You’re in',
    detail: 'The organizer can see your pick. Change it here any time before they confirm.',
  },
  maybe: {
    heading: 'Marked maybe',
    detail: 'The organizer knows you’re a maybe. Come back to this link to firm it up.',
  },
  declined: {
    heading: 'Marked can’t make it',
    detail: 'The organizer knows you’re out. Change your mind here if that shifts.',
  },
};

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
  const [checkEmail, setCheckEmail] = useState<string | null>(null);
  const [submittingChoice, setSubmittingChoice] = useState<Choice | null>(null);
  const [submittedChoice, setSubmittedChoice] = useState<Choice | null>(null);

  const browserZone = useMemo(() => browserTimezone(), []);

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
          setError(loadError instanceof Error ? loadError.message : 'Could not open this link.');
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
  const showsLocalTime = browserZone !== organizerTimezone;

  async function submit(choice: Choice) {
    if (!event) return;

    if (!isTokenMode) {
      if (!displayName.trim()) {
        setError('Add your name so the organizer knows who answered.');
        return;
      }
      if (!email.trim()) {
        setError('Add your email — use the one you were invited with if you have it.');
        return;
      }
    }
    if (choice === 'picked' && !selectedProposalId) {
      setError('Tap a time first, then pick it.');
      return;
    }

    setError(null);
    setCheckEmail(null);
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

      setSubmittedChoice(choice);
      if (typeof window !== 'undefined') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not save your answer.');
    } finally {
      setSubmittingChoice(null);
    }
  }

  if (error && !event) {
    const expired = /expired/i.test(error);
    return (
      <main className="wrap-narrow page">
        <div className="head">
          <h1 className="title-page">{expired ? 'This link has expired' : 'This link didn’t open'}</h1>
          <p className="lede">
            {expired
              ? 'Ask whoever sent it for a fresh one — it only takes them a tap.'
              : error}
          </p>
        </div>
      </main>
    );
  }

  if (!event) {
    return (
      <main className="wrap-narrow page" aria-busy="true">
        <div className="head">
          <div className="skel" style={{ height: '2.5rem', width: '70%' }} />
          <div className="skel" style={{ height: '1rem', width: '40%' }} />
        </div>
        <div className="skel" style={{ height: '6rem', borderRadius: '10px' }} />
        <div className="skel" style={{ height: '6rem', borderRadius: '10px' }} />
        <span className="sr-only">Loading</span>
      </main>
    );
  }

  const metaBits = [formatDuration(event.duration_min), event.location].filter(Boolean);

  if (isConfirmed && confirmedEvent) {
    const hasTimes = Boolean(confirmedEvent.start_at && confirmedEvent.end_at);
    return (
      <main className="wrap-narrow page">
        <div className="head reveal">
          <span className="pill" data-tone="done">
            Confirmed
          </span>
          <h1 className="title-page">{event.title}</h1>
          <p className="lede">This is confirmed. Save it to your calendar and you&rsquo;re done.</p>
        </div>

        <section className="card card-ink reveal" style={{ ['--i' as string]: 1 }}>
          {hasTimes ? (
            <Slot
              startIso={confirmedEvent.start_at as string}
              endIso={confirmedEvent.end_at as string}
              timezone={browserZone}
              state="won"
              note={showsLocalTime ? `Shown in your time — ${zoneLabel(browserZone)}` : undefined}
            />
          ) : (
            <p>The organizer is finalizing the time.</p>
          )}

          <ul className="stack-tight">
            {confirmedEvent.location ? (
              <li className="muted">Where: {confirmedEvent.location}</li>
            ) : null}
            {confirmedEvent.video_link ? (
              <li className="muted">
                Join:{' '}
                <a href={confirmedEvent.video_link} rel="noreferrer" target="_blank">
                  {confirmedEvent.video_link}
                </a>
              </li>
            ) : null}
            {confirmedEvent.notes ? <li className="muted">{confirmedEvent.notes}</li> : null}
          </ul>

          {hasTimes ? (
            <div className="row">
              <a
                className="btn btn-quiet"
                href={buildGoogleCalendarUrl({
                  title: event.title,
                  startIso: confirmedEvent.start_at as string,
                  endIso: confirmedEvent.end_at as string,
                  details: confirmedEvent.notes ?? '',
                  location: confirmedEvent.location ?? confirmedEvent.video_link ?? '',
                })}
                rel="noreferrer"
                target="_blank"
              >
                Add to Google Calendar
              </a>
              <a
                className="btn btn-quiet"
                href={buildOutlookCalendarUrl({
                  title: event.title,
                  startIso: confirmedEvent.start_at as string,
                  endIso: confirmedEvent.end_at as string,
                  details: confirmedEvent.notes ?? '',
                  location: confirmedEvent.location ?? confirmedEvent.video_link ?? '',
                })}
                rel="noreferrer"
                target="_blank"
              >
                Add to Outlook
              </a>
              {confirmedEvent.artifact_url ? (
                <a
                  className="btn btn-quiet"
                  href={confirmedEvent.artifact_url}
                  rel="noreferrer"
                  target="_blank"
                >
                  Apple Calendar
                </a>
              ) : null}
            </div>
          ) : null}
        </section>
      </main>
    );
  }

  const answer = submittedChoice ? ANSWER_COPY[submittedChoice] : null;
  const selectedShape = selectedProposalId
    ? (() => {
        const found = event.proposals.find((proposal) => proposal.id === selectedProposalId);
        return found ? shapeSlot(found.start_at, found.end_at, browserZone) : null;
      })()
    : null;

  return (
    <main className="wrap-narrow page">
      <div className="head reveal">
        <h1 className="title-page">{event.title}</h1>
        <p className="muted">{metaBits.join(' · ')}</p>
        {isTokenMode ? (
          <p className="lede">
            Responding as <strong>{invitedAs?.display_name || invitedAs?.email || 'you'}</strong>.
          </p>
        ) : (
          <p className="lede">Tap the times that work. No account, no app.</p>
        )}
      </div>

      {checkEmail ? (
        <section className="card reveal" data-tone="info">
          <h2 className="title-card">Check your email</h2>
          <p className="muted">{checkEmail}</p>
        </section>
      ) : null}

      {answer && !checkEmail ? (
        <section className="card reveal" style={{ ['--i' as string]: 1 }} role="status">
          <div className="row-between">
            <h2 className="title-card">{answer.heading}</h2>
            <span className="pill" data-tone={submittedChoice === 'picked' ? 'live' : 'waiting'}>
              Saved
            </span>
          </div>
          {selectedShape && submittedChoice !== 'declined' ? (
            <p className="muted">You picked {selectedShape.full}.</p>
          ) : null}
          <p className="muted">{answer.detail}</p>
        </section>
      ) : null}

      <form className="stack-loose" onSubmit={(formEvent) => formEvent.preventDefault()}>
        {!isTokenMode ? (
          <section className="card reveal" style={{ ['--i' as string]: 2 }}>
            <h2 className="title-card">Who are you?</h2>
            <div className="pair">
              <label className="field">
                <span className="field-label">Your name</span>
                <input
                  className="input"
                  value={displayName}
                  onChange={(formEvent) => setDisplayName(formEvent.target.value)}
                  placeholder="Alex"
                />
              </label>
              <label className="field">
                <span className="field-label">Email</span>
                <input
                  className="input"
                  type="email"
                  value={email}
                  onChange={(formEvent) => setEmail(formEvent.target.value)}
                  placeholder="alex@example.com"
                />
                <span className="field-hint">
                  Use the one you were invited with, if you got an invite.
                </span>
              </label>
            </div>
            <label className="field">
              <span className="field-label">Phone (optional)</span>
              <input
                className="input"
                value={phone}
                onChange={(formEvent) => setPhone(formEvent.target.value)}
                placeholder="555-222-0101"
              />
            </label>
          </section>
        ) : null}

        <section className="band reveal" style={{ ['--i' as string]: 3 }}>
          <div className="band-head">
            <h2 className="title-card">Pick what works</h2>
            <span className="muted">
              {showsLocalTime ? `Your time · ${zoneLabel(browserZone)}` : zoneLabel(browserZone)}
            </span>
          </div>
          <ul className="stack-tight">
            {event.proposals.map((proposal, index) => (
              <li key={proposal.id}>
                <SlotChoice
                  startIso={proposal.start_at}
                  endIso={proposal.end_at}
                  timezone={browserZone}
                  index={index + 1}
                  selected={selectedProposalId === proposal.id}
                  onSelect={() => setSelectedProposalId(proposal.id)}
                />
              </li>
            ))}
          </ul>

          <label className="field">
            <span className="field-label">Add a note (optional)</span>
            <textarea
              className="input"
              rows={2}
              value={comment}
              onChange={(formEvent) => setComment(formEvent.target.value)}
              placeholder="After 7 works best for me"
            />
          </label>
        </section>

        {error ? (
          <p className="note" data-tone="bad" role="alert">
            {error}
          </p>
        ) : null}

        <div className="dock">
          <button
            className="btn"
            disabled={submittingChoice !== null || !selectedShape}
            onClick={() => submit('picked')}
            type="button"
          >
            {submittingChoice === 'picked'
              ? 'Saving…'
              : selectedShape
                ? `Pick ${selectedShape.weekday} ${selectedShape.day}`
                : 'Tap a time first'}
          </button>
          <button
            className="btn btn-quiet"
            disabled={submittingChoice !== null}
            onClick={() => submit('maybe')}
            type="button"
          >
            {submittingChoice === 'maybe' ? 'Saving…' : 'Maybe'}
          </button>
          <button
            className="btn btn-quiet"
            disabled={submittingChoice !== null}
            onClick={() => submit('declined')}
            type="button"
          >
            {submittingChoice === 'declined' ? 'Saving…' : 'Can’t make it'}
          </button>
        </div>
      </form>
    </main>
  );
}
