'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import {
  finalizeRequest,
  getOrganizerRequest,
  pingNonResponders,
  updateReminderSettings,
  type OrganizerRequestDetail,
  type ReminderPolicy,
} from '../../../lib/api';
import { rememberRequest } from '../../../lib/recents';
import { Slot, SlotChoice, Tally, type SlotState } from '../../../components/Slot';
import { formatDuration, formatMoment, relativeTime, shapeSlot, zoneLabel } from '../../../lib/time';

function reminderReason(reason: string): string {
  switch (reason) {
    case 'manual_ping':
      return 'you nudged them';
    case 'deadline':
      return 'deadline is close';
    case 'scheduled':
      return 'scheduled follow-up';
    default:
      return reason;
  }
}

function toLocalDateTimeInput(iso: string | null) {
  if (!iso) {
    return '';
  }

  const date = new Date(iso);
  const pad = (value: number) => value.toString().padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function personName(person: {
  display_name?: string | null;
  email?: string | null;
  phone?: string | null;
}): string {
  return person.display_name ?? person.email ?? person.phone ?? 'Guest';
}

async function copyToClipboard(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    // Older browsers and insecure origins have no clipboard API.
    const field = document.createElement('textarea');
    field.value = value;
    field.setAttribute('readonly', '');
    field.style.position = 'fixed';
    field.style.opacity = '0';
    document.body.appendChild(field);
    field.select();
    document.execCommand('copy');
    document.body.removeChild(field);
  }
}

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const requestId = Array.isArray(params.id) ? params.id[0] : params.id;
  const [request, setRequest] = useState<OrganizerRequestDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [shortlistId, setShortlistId] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [pingMessage, setPingMessage] = useState<string | null>(null);
  const [isPinging, setIsPinging] = useState(false);
  const [remindersEnabledDraft, setRemindersEnabledDraft] = useState(true);
  const [deadlineDraft, setDeadlineDraft] = useState('');
  const [policyDraft, setPolicyDraft] = useState<ReminderPolicy>({
    initial_hours: 12,
    followup_hours: 24,
    max_per_participant: 3,
  });
  const [isSavingReminders, setIsSavingReminders] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const next = await getOrganizerRequest(requestId);
        if (!cancelled) {
          setRequest(next);
          rememberRequest({
            id: next.id,
            title: next.title,
            createdAt: new Date().toISOString(),
            status: next.status,
          });
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load this request.');
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  useEffect(() => {
    if (!request) {
      return;
    }
    setRemindersEnabledDraft(request.reminders.enabled);
    setDeadlineDraft(toLocalDateTimeInput(request.reminders.response_deadline));
    setPolicyDraft({
      initial_hours: request.reminders.policy.initial_hours,
      followup_hours: request.reminders.policy.followup_hours,
      max_per_participant: request.reminders.policy.max_per_participant,
    });
  }, [request]);

  async function copy(value: string, key: string) {
    await copyToClipboard(value);
    setCopied(key);
    window.setTimeout(() => setCopied((current) => (current === key ? null : current)), 1600);
  }

  async function confirmOption(proposalId: string) {
    setIsConfirming(true);
    setError(null);
    try {
      await finalizeRequest(requestId, proposalId);
      const next = await getOrganizerRequest(requestId);
      setRequest(next);
      setShortlistId(null);
    } catch (confirmError) {
      setError(
        confirmError instanceof Error ? confirmError.message : 'Could not confirm that time.',
      );
    } finally {
      setIsConfirming(false);
    }
  }

  async function saveReminderState() {
    setError(null);
    setPingMessage(null);
    setIsSavingReminders(true);
    try {
      await updateReminderSettings(requestId, {
        reminders_enabled: remindersEnabledDraft,
        response_deadline: deadlineDraft ? new Date(deadlineDraft).toISOString() : null,
        reminder_policy: {
          initial_hours: policyDraft.initial_hours,
          followup_hours: policyDraft.followup_hours,
          max_per_participant: policyDraft.max_per_participant,
        },
      });
      const next = await getOrganizerRequest(requestId);
      setRequest(next);
      setPingMessage('Reminder settings saved.');
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save those settings.');
    } finally {
      setIsSavingReminders(false);
    }
  }

  async function pingOutstanding() {
    setError(null);
    setPingMessage(null);
    setIsPinging(true);
    try {
      const result = await pingNonResponders(requestId);
      const parts: string[] = [];
      if (result.sent_count > 0) {
        parts.push(`Nudged ${result.sent_count} ${result.sent_count === 1 ? 'person' : 'people'}`);
      }
      if (result.skipped_count > 0) {
        parts.push(
          `${result.skipped_count} skipped — they have already had the maximum number of reminders`,
        );
      }
      if (result.sent_count === 0 && result.skipped_count === 0) {
        parts.push('Nobody to nudge');
      }
      parts.push(`${result.outstanding_count} still to answer`);
      setPingMessage(parts.join(' · '));
      const next = await getOrganizerRequest(requestId);
      setRequest(next);
    } catch (pingError) {
      setError(pingError instanceof Error ? pingError.message : 'Could not send those nudges.');
    } finally {
      setIsPinging(false);
    }
  }

  function updatePolicyField(field: keyof ReminderPolicy, raw: string) {
    const next = Number(raw);
    if (!Number.isFinite(next) || next < 1) {
      return;
    }
    setPolicyDraft((current) => ({ ...current, [field]: Math.floor(next) }));
  }

  if (error && !request) {
    return (
      <main className="wrap-narrow page">
        <div className="head">
          <h1 className="title-page">Can&rsquo;t open this request</h1>
          <p className="note" data-tone="bad">
            {error}
          </p>
          <p>
            <Link href="/create">Start a new one</Link>
          </p>
        </div>
      </main>
    );
  }

  if (!request) {
    return (
      <main className="wrap-narrow page" aria-busy="true">
        <div className="head">
          <div className="skel" style={{ height: '2.5rem', width: '60%' }} />
          <div className="skel" style={{ height: '1rem', width: '35%' }} />
        </div>
        <div className="skel" style={{ height: '9rem', borderRadius: '16px' }} />
        <div className="skel" style={{ height: '16rem', borderRadius: '16px' }} />
        <span className="sr-only">Loading request</span>
      </main>
    );
  }

  const shareUrl = request.share?.url ?? null;
  const confirmed = request.confirmed_event;
  const confirmedOption = confirmed
    ? request.proposals.find((proposal) => proposal.id === confirmed.proposal_id) ?? null
    : null;
  const { responded_count: responded, participant_count: total, outstanding_count: outstanding } =
    request.progress;
  const percent = total > 0 ? Math.round((responded / total) * 100) : 0;
  const deadlineWhen = relativeTime(request.reminders.response_deadline);

  const eventType = request.event_type
    ? request.event_type.charAt(0).toUpperCase() + request.event_type.slice(1)
    : null;
  const metaBits = [
    eventType,
    formatDuration(request.duration_min),
    zoneLabel(request.timezone),
    request.location,
  ].filter(Boolean);
  const shortlisted = shortlistId
    ? request.proposals.find((proposal) => proposal.id === shortlistId) ?? null
    : null;
  const shortlistShape = shortlisted
    ? shapeSlot(shortlisted.start_at, shortlisted.end_at, request.timezone)
    : null;

  return (
    <main className="wrap-narrow page">
      <div className="head reveal">
        <div className="row-between">
          <span className="label">{confirmed ? 'Booked' : 'Collecting answers'}</span>
          <span className="pill" data-tone={confirmed ? 'done' : outstanding > 0 ? 'waiting' : 'live'}>
            {confirmed ? 'Confirmed' : outstanding > 0 ? `${outstanding} to answer` : 'All in'}
          </span>
        </div>
        <h1 className="title-page">{request.title}</h1>
        <p className="muted">{metaBits.join(' · ')}</p>
        {request.video_link ? (
          <p className="muted">
            <a href={request.video_link} rel="noreferrer" target="_blank">
              {request.video_link}
            </a>
          </p>
        ) : null}
      </div>

      {error ? (
        <p className="note" data-tone="bad" role="alert">
          {error}
        </p>
      ) : null}

      {confirmed ? (
        <section className="card card-ink reveal" style={{ ['--i' as string]: 1 }}>
          <div className="row-between">
            <h2 className="title-card">It&rsquo;s booked</h2>
            <span className="muted">
              {confirmed.provider ? `Written to ${confirmed.provider}` : 'No calendar connected'}
            </span>
          </div>
          {confirmedOption ? (
            <Slot
              startIso={confirmedOption.start_at}
              endIso={confirmedOption.end_at}
              timezone={request.timezone}
              state="won"
            />
          ) : (
            <p>{formatMoment(confirmed.start_at, request.timezone)}</p>
          )}
          <div className="row">
            {confirmed.artifact_url ? (
              <a className="btn btn-quiet" href={confirmed.artifact_url} rel="noreferrer" target="_blank">
                Download the invite
              </a>
            ) : null}
            <a
              className="btn btn-quiet"
              href={`/events/${request.id}/respond`}
              rel="noreferrer"
              target="_blank"
            >
              Open attendee view
            </a>
          </div>
          <p className="muted">
            Everyone with an email on file was sent the invite. Confirming again updates the same
            calendar event instead of sending a duplicate.
          </p>
        </section>
      ) : shareUrl ? (
        <section className="card reveal" style={{ ['--i' as string]: 1 }}>
          <h2 className="title-card">Send this link</h2>
          <div className="copyfield">
            <code>{shareUrl}</code>
            <button className="btn" onClick={() => copy(shareUrl, 'share')} type="button">
              {copied === 'share' ? 'Copied' : 'Copy link'}
            </button>
          </div>
          <p className="field-hint">
            Paste it in the group chat. Anyone who opens it can answer without an account — and each
            person you added also has their own link below.
          </p>
          <div className="row">
            <Link className="btn btn-text btn-small" href={`/events/${request.id}/respond`}>
              See what they see
            </Link>
          </div>
        </section>
      ) : null}

      <section className="band reveal" style={{ ['--i' as string]: 2 }}>
        <div className="band-head">
          <h2 className="title-card">{confirmed ? 'How they voted' : 'The times'}</h2>
          {!confirmed ? (
            <span className="muted num">
              {responded} of {total} answered
            </span>
          ) : null}
        </div>

        {request.proposals.length === 0 ? (
          <p className="note">
            This request has no times on it yet. Nobody can answer until it does.
          </p>
        ) : null}

        <ul className="stack-tight">
          {request.proposals.map((proposal, index) => {
            const tally = request.tallies[proposal.id] ?? { picked: 0, maybe: 0, declined: 0 };
            const state: SlotState = confirmed
              ? proposal.id === confirmed.proposal_id
                ? 'won'
                : 'lost'
              : 'open';

            const tallyMarks = (
              <Tally
                picked={tally.picked}
                maybe={tally.maybe}
                declined={tally.declined}
                total={total}
              />
            );

            return (
              <li key={proposal.id}>
                {confirmed ? (
                  <Slot
                    startIso={proposal.start_at}
                    endIso={proposal.end_at}
                    timezone={request.timezone}
                    index={index + 1}
                    state={state}
                  >
                    {tallyMarks}
                  </Slot>
                ) : (
                  <SlotChoice
                    startIso={proposal.start_at}
                    endIso={proposal.end_at}
                    timezone={request.timezone}
                    index={index + 1}
                    selected={shortlistId === proposal.id}
                    onSelect={() =>
                      setShortlistId((current) => (current === proposal.id ? null : proposal.id))
                    }
                  >
                    {tallyMarks}
                  </SlotChoice>
                )}
              </li>
            );
          })}
        </ul>

        {!confirmed && request.proposals.length > 0 ? (
          shortlistShape ? (
            <div className="card">
              <p className="muted">
                Booking {shortlistShape.full} sends everyone the invite and writes it to your
                calendar.
              </p>
              <div className="row">
                <button
                  className="btn"
                  disabled={isConfirming}
                  onClick={() => confirmOption(shortlistId as string)}
                  type="button"
                >
                  {isConfirming
                    ? 'Booking…'
                    : `Confirm ${shortlistShape.weekday} ${shortlistShape.day}`}
                </button>
                <button
                  className="btn btn-text"
                  onClick={() => setShortlistId(null)}
                  type="button"
                >
                  Keep waiting
                </button>
              </div>
            </div>
          ) : (
            <p className="field-hint">Tap the time you want, then confirm it.</p>
          )
        ) : null}
      </section>

      <section className="card reveal" style={{ ['--i' as string]: 3 }}>
        <div className="row-between">
          <h2 className="title-card">
            Who&rsquo;s in{' '}
            <span className="muted num">
              — {responded} of {total} answered
            </span>
          </h2>
          {outstanding > 0 && !confirmed ? (
            <button
              className="btn btn-quiet btn-small"
              disabled={isPinging}
              onClick={pingOutstanding}
              type="button"
            >
              {isPinging ? 'Sending…' : `Nudge the ${outstanding} still out`}
            </button>
          ) : null}
        </div>

        {total > 0 ? (
          <div className="meter" role="img" aria-label={`${responded} of ${total} answered`}>
            <span className="meter-fill" style={{ width: `${percent}%` }} />
          </div>
        ) : null}

        {request.participants.length === 0 ? (
          <p className="note">Nobody has been invited yet.</p>
        ) : (
          <ul className="people">
            {request.participants.map((participant) => {
              const answered = participant.status === 'responded';
              return (
                <li className="person" key={participant.id}>
                  <span className="dot" data-tone={answered ? 'in' : 'waiting'} />
                  <span className="person-name">
                    <strong>{personName(participant)}</strong>
                    <span>
                      {answered
                        ? `Answered ${relativeTime(participant.responded_at) ?? ''}`.trim()
                        : participant.email ?? participant.phone ?? 'No contact on file'}
                    </span>
                  </span>
                  {participant.invite_url ? (
                    <button
                      className="btn btn-quiet btn-small"
                      onClick={() => copy(participant.invite_url as string, participant.id)}
                      type="button"
                    >
                      {copied === participant.id ? 'Copied' : 'Copy their link'}
                    </button>
                  ) : (
                    <span className="muted">No link</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {pingMessage ? (
          <p className="note" data-tone="good" role="status">
            {pingMessage}
          </p>
        ) : null}

        {request.notes ? <p className="field-hint">Your note to them: {request.notes}</p> : null}
      </section>

      <details className="fold reveal" style={{ ['--i' as string]: 4 }}>
        <summary>
          Reminders —{' '}
          {request.reminders.enabled
            ? `on, ${request.reminders.sent_count} sent so far`
            : 'off'}
          {deadlineWhen && !confirmed ? `, answers due ${deadlineWhen}` : ''}
        </summary>
        <div className="fold-body">
          <label className="check">
            <input
              checked={remindersEnabledDraft}
              onChange={(event) => setRemindersEnabledDraft(event.target.checked)}
              type="checkbox"
            />
            <span>Nudge people who haven&rsquo;t answered</span>
          </label>

          <div className="pair">
            <label className="field">
              <span className="field-label">Answers due by</span>
              <input
                className="input"
                type="datetime-local"
                value={deadlineDraft}
                onChange={(event) => setDeadlineDraft(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">First nudge after (hours)</span>
              <input
                className="input"
                type="number"
                min={1}
                max={720}
                value={policyDraft.initial_hours}
                onChange={(event) => updatePolicyField('initial_hours', event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Then every (hours)</span>
              <input
                className="input"
                type="number"
                min={1}
                max={720}
                value={policyDraft.followup_hours}
                onChange={(event) => updatePolicyField('followup_hours', event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Never more than (per person)</span>
              <input
                className="input"
                type="number"
                min={1}
                max={10}
                value={policyDraft.max_per_participant}
                onChange={(event) => updatePolicyField('max_per_participant', event.target.value)}
              />
            </label>
          </div>

          <div className="row">
            <button
              className="btn btn-quiet btn-small"
              disabled={isSavingReminders}
              onClick={saveReminderState}
              type="button"
            >
              {isSavingReminders ? 'Saving…' : 'Save reminder settings'}
            </button>
            <span className="field-hint">
              Last nudge: {formatMoment(request.reminders.last_reminded_at, request.timezone)}
            </span>
          </div>

          {request.reminders.history.length > 0 ? (
            <ul className="people">
              {request.reminders.history.map((entry) => {
                const participant = request.participants.find(
                  (candidate) => candidate.id === entry.participant_id,
                );
                return (
                  <li className="person" key={entry.id}>
                    <span className="dot" data-tone="out" />
                    <span className="person-name">
                      <strong>{participant ? personName(participant) : entry.target}</strong>
                      <span>
                        {entry.channel} · nudge #{entry.sequence} · {reminderReason(entry.reason)}
                      </span>
                    </span>
                    <span className="muted num">
                      {formatMoment(entry.created_at, request.timezone)}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="field-hint">No reminders have gone out yet.</p>
          )}
        </div>
      </details>
    </main>
  );
}
