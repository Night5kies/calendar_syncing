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
import { formatDateTime, formatRange } from '../../../lib/types';

function describeReminderReason(reason: string): string {
  switch (reason) {
    case 'manual_ping':
      return 'Manual ping';
    case 'deadline':
      return 'Deadline reminder';
    case 'scheduled':
      return 'Scheduled reminder';
    default:
      return reason;
  }
}

function describeReminderStatus(status: string): string {
  if (!status) {
    return 'queued';
  }
  return status;
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

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const requestId = Array.isArray(params.id) ? params.id[0] : params.id;
  const [request, setRequest] = useState<OrganizerRequestDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);
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

  async function copySharePath() {
    if (!request?.share) {
      return;
    }
    await navigator.clipboard.writeText(request.share.url);
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
      setError(saveError instanceof Error ? saveError.message : 'Unable to save reminder settings.');
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
        parts.push(`Queued ${result.sent_count} reminder${result.sent_count === 1 ? '' : 's'}`);
      }
      if (result.skipped_count > 0) {
        parts.push(`skipped ${result.skipped_count} (cap or duplicate)`);
      }
      parts.push(`${result.outstanding_count} still outstanding`);
      setPingMessage(parts.join(' - '));
      const next = await getOrganizerRequest(requestId);
      setRequest(next);
    } catch (pingError) {
      setError(pingError instanceof Error ? pingError.message : 'Unable to ping non-responders.');
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
          <h1>Loading request...</h1>
        </div>
      </main>
    );
  }

  const shareUrl = request.share?.url ?? null;
  const confirmedOption = request.confirmed_event
    ? request.proposals.find((proposal) => proposal.id === request.confirmed_event?.proposal_id) ?? null
    : null;

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Organizer view</p>
        <h1>{request.title}</h1>
        <p className="lede">
          {request.duration_min} min - {request.timezone}
          {request.event_type ? ` - ${request.event_type}` : ''}
        </p>
        {request.location || request.video_link ? (
          <p className="helper-copy">
            {request.location ? <span>{request.location}</span> : null}
            {request.location && request.video_link ? <span> - </span> : null}
            {request.video_link ? (
              <a href={request.video_link} rel="noreferrer" target="_blank">
                {request.video_link}
              </a>
            ) : null}
          </p>
        ) : null}
      </div>

      <section className="grid-two">
        <article className="panel">
          <p className="section-label">Participants</p>
          <ul className="stack-form" style={{ gap: '0.5rem' }}>
            {request.participants.map((participant) => (
              <li key={participant.id} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <strong>
                  {participant.display_name ?? participant.email ?? participant.phone ?? 'Guest'}
                  {participant.status === 'responded' ? ' ✓' : ''}
                </strong>
                {participant.invite_url ? (
                  <code style={{ fontSize: '0.75rem', wordBreak: 'break-all' }}>
                    {participant.invite_url}
                  </code>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="helper-copy">
            {request.progress.responded_count}/{request.progress.participant_count} responded -{' '}
            {request.progress.outstanding_count} outstanding
          </p>
          <p className="helper-copy">
            Each invitee has a private link above. Reminders send each person their own link.
          </p>
          {request.notes ? <p className="helper-copy">{request.notes}</p> : null}
        </article>

        <article className="panel">
          <p className="section-label">Share</p>
          {shareUrl ? (
            <>
              <div className="share-row">
                <code>{shareUrl}</code>
                <button className="button button-secondary" onClick={copySharePath} type="button">
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="button-group">
                <Link className="button button-primary" href={shareUrl}>
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
            <p className="section-label">Reminders</p>
            <h2>Follow-up state</h2>
          </div>
          <button
            className="button button-secondary"
            disabled={isPinging || request.outstanding_participants.length === 0}
            onClick={pingOutstanding}
            type="button"
          >
            {isPinging ? 'Queueing...' : 'Ping non-responders'}
          </button>
        </div>
        <div className="flat-list">
          <div className="stat-row">
            <span>Auto reminders</span>
            <strong>{request.reminders.enabled ? 'On' : 'Off'}</strong>
          </div>
          <div className="stat-row">
            <span>Response deadline</span>
            <strong>{formatDateTime(request.reminders.response_deadline, request.timezone)}</strong>
          </div>
          <div className="stat-row">
            <span>Last reminder</span>
            <strong>{formatDateTime(request.reminders.last_reminded_at, request.timezone)}</strong>
          </div>
          <div className="stat-row">
            <span>Total queued reminders</span>
            <strong>{request.reminders.sent_count}</strong>
          </div>
        </div>
        <div className="field-grid">
          <div className="field field-checkbox">
            <span>Reminder policy</span>
            <label className="checkbox-row">
              <input
                checked={remindersEnabledDraft}
                onChange={(event) => setRemindersEnabledDraft(event.target.checked)}
                type="checkbox"
              />
              <span>Enable reminders for outstanding participants</span>
            </label>
          </div>
          <label className="field">
            <span>Response deadline</span>
            <input
              type="datetime-local"
              value={deadlineDraft}
              onChange={(event) => setDeadlineDraft(event.target.value)}
            />
          </label>
          <label className="field">
            <span>First reminder after (hours since send)</span>
            <input
              type="number"
              min={1}
              max={720}
              value={policyDraft.initial_hours}
              onChange={(event) => updatePolicyField('initial_hours', event.target.value)}
            />
          </label>
          <label className="field">
            <span>Follow-up cadence (hours)</span>
            <input
              type="number"
              min={1}
              max={720}
              value={policyDraft.followup_hours}
              onChange={(event) => updatePolicyField('followup_hours', event.target.value)}
            />
          </label>
          <label className="field">
            <span>Max reminders per participant</span>
            <input
              type="number"
              min={1}
              max={10}
              value={policyDraft.max_per_participant}
              onChange={(event) => updatePolicyField('max_per_participant', event.target.value)}
            />
          </label>
        </div>
        <div className="button-group">
          <button
            className="button button-secondary"
            disabled={isSavingReminders}
            onClick={saveReminderState}
            type="button"
          >
            {isSavingReminders ? 'Saving...' : 'Save reminder settings'}
          </button>
        </div>
        {request.outstanding_participants.length > 0 ? (
          <p className="helper-copy">
            Waiting on{' '}
            {request.outstanding_participants
              .map((participant) => participant.display_name ?? participant.email ?? participant.phone ?? 'Guest')
              .join(', ')}
          </p>
        ) : (
          <p className="helper-copy">Everyone has responded.</p>
        )}
        {pingMessage ? <p className="success-text">{pingMessage}</p> : null}
        {request.reminders.history.length > 0 ? (
          <div className="reminder-history">
            <p className="section-label">Reminder history</p>
            <ul className="reminder-history-list">
              {request.reminders.history.map((entry) => {
                const participant = request.participants.find(
                  (candidate) => candidate.id === entry.participant_id,
                );
                const who =
                  participant?.display_name ??
                  participant?.email ??
                  participant?.phone ??
                  entry.target;
                return (
                  <li key={entry.id} className="reminder-history-item">
                    <span className="reminder-history-time">
                      {formatDateTime(entry.created_at, request.timezone)}
                    </span>
                    <span className="reminder-history-meta">
                      <strong>{who}</strong>
                      <span> - {entry.channel}</span>
                      <span> - #{entry.sequence}</span>
                      <span> - {describeReminderReason(entry.reason)}</span>
                      <span> - {describeReminderStatus(entry.status)}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
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
                    {tally.picked} picked - {tally.maybe} maybe
                  </p>
                </div>
                <button
                  className="button button-secondary"
                  disabled={loadingProposalId === proposal.id}
                  onClick={() => confirmOption(proposal.id)}
                  type="button"
                >
                  {loadingProposalId === proposal.id ? 'Confirming...' : 'Confirm winner'}
                </button>
              </article>
            );
          })}
        </div>
      </section>

      {request.confirmed_event ? (
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-label">Confirmation</p>
              <h2>Booked artifact</h2>
            </div>
            <span className="status-pill status-confirmed">confirmed</span>
          </div>
          <div className="flat-list">
            <div className="stat-row">
              <span>Winning option</span>
              <strong>
                {confirmedOption
                  ? formatRange(confirmedOption.start_at, confirmedOption.end_at, request.timezone)
                  : formatDateTime(request.confirmed_event.start_at, request.timezone)}
              </strong>
            </div>
            <div className="stat-row">
              <span>Calendar write-back</span>
              <strong>
                {request.confirmed_event.provider
                  ? `Sent to ${request.confirmed_event.provider}`
                  : 'Not connected'}
              </strong>
            </div>
            <div className="stat-row">
              <span>Provider event id</span>
              <strong>{request.confirmed_event.provider_event_id ?? 'Unavailable'}</strong>
            </div>
          </div>
          <p className="helper-copy">
            The request is confirmed. Attendees with email on file were sent the ICS automatically
            (file outbox in local mode). Re-finalizing the same event won&rsquo;t double-send — the
            invite job dedupes per scheduled event + participant.
          </p>
          <div className="button-group">
            {request.confirmed_event.artifact_url ? (
              <a
                className="button button-primary"
                href={request.confirmed_event.artifact_url}
                rel="noreferrer"
                target="_blank"
              >
                Download ICS
              </a>
            ) : null}
            <a
              className="button button-secondary"
              href={`/events/${request.id}/respond`}
              rel="noreferrer"
              target="_blank"
            >
              Open attendee view
            </a>
          </div>
          {request.participants.length > 0 ? (
            <ul className="confirmed-recipients">
              {request.participants.map((participant) => (
                <li key={participant.id}>
                  <strong>
                    {participant.display_name ?? participant.email ?? participant.phone ?? 'Guest'}
                  </strong>
                  <span className="helper-copy">
                    {participant.email
                      ? `Invite emailed to ${participant.email}`
                      : 'No email on file — share the attendee link manually'}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
