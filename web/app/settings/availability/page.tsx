'use client';

import { useEffect, useMemo, useState } from 'react';

import {
  createAvailabilityBlock,
  deleteAvailabilityBlock,
  disconnectGoogle,
  getAvailabilityBlocks,
  getAvailabilityRules,
  getCalendarConnections,
  startGoogleConnect,
  upsertAvailabilityRule,
  type AvailabilityBlock,
  type AvailabilityWeekday,
  type AvailabilityWeeklyHours,
  type CalendarConnectionPayload,
} from '../../../lib/api';
import { browserTimezone, formatMoment } from '../../../lib/time';

const WEEKDAYS: { id: AvailabilityWeekday; label: string }[] = [
  { id: 'mon', label: 'Monday' },
  { id: 'tue', label: 'Tuesday' },
  { id: 'wed', label: 'Wednesday' },
  { id: 'thu', label: 'Thursday' },
  { id: 'fri', label: 'Friday' },
  { id: 'sat', label: 'Saturday' },
  { id: 'sun', label: 'Sunday' },
];

const BLOCK_LABEL: Record<AvailabilityBlock['type'], string> = {
  private: 'Private',
  busy: 'Busy',
  ooo: 'Out of office',
};

function emptyHours(): AvailabilityWeeklyHours {
  return { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };
}

function defaultHours(): AvailabilityWeeklyHours {
  return {
    mon: [{ start: '09:00', end: '17:00' }],
    tue: [{ start: '09:00', end: '17:00' }],
    wed: [{ start: '09:00', end: '17:00' }],
    thu: [{ start: '09:00', end: '17:00' }],
    fri: [{ start: '09:00', end: '17:00' }],
    sat: [],
    sun: [],
  };
}

function isoFromLocal(value: string) {
  return value ? new Date(value).toISOString() : '';
}

export default function AvailabilitySettingsPage() {
  const [timezone, setTimezone] = useState<string>('America/New_York');
  const [hours, setHours] = useState<AvailabilityWeeklyHours>(defaultHours());
  const [blocks, setBlocks] = useState<AvailabilityBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedRulesAt, setSavedRulesAt] = useState<string | null>(null);
  const [isSavingRules, setIsSavingRules] = useState(false);

  const [blockStart, setBlockStart] = useState('');
  const [blockEnd, setBlockEnd] = useState('');
  const [blockType, setBlockType] = useState<AvailabilityBlock['type']>('private');
  const [isCreatingBlock, setIsCreatingBlock] = useState(false);

  const [connections, setConnections] = useState<CalendarConnectionPayload[]>([]);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [connectionMessage, setConnectionMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [rulesPayload, blocksPayload, connectionsPayload] = await Promise.all([
          getAvailabilityRules(),
          getAvailabilityBlocks(),
          getCalendarConnections().catch(() => ({ connections: [] as CalendarConnectionPayload[] })),
        ]);
        if (cancelled) return;
        const rule = rulesPayload.rules[0];
        if (rule) {
          setTimezone(rule.timezone);
          setHours({ ...emptyHours(), ...(rule.weekly_hours ?? {}) });
        } else {
          setTimezone(browserTimezone());
        }
        setBlocks(blocksPayload.blocks);
        setConnections(connectionsPayload.connections);
        if (typeof window !== 'undefined') {
          const params = new URLSearchParams(window.location.search);
          if (params.get('google') === 'connected') {
            setConnectionMessage('Google Calendar connected.');
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error ? loadError.message : 'Could not load your availability.',
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const googleConnection = useMemo(
    () => connections.find((connection) => connection.provider === 'google') ?? null,
    [connections],
  );

  async function connectGoogle() {
    setError(null);
    setConnectionMessage(null);
    setIsConnecting(true);
    try {
      const returnTo =
        typeof window !== 'undefined' ? window.location.origin + window.location.pathname : '/';
      const { authorize_url } = await startGoogleConnect(returnTo);
      window.location.href = authorize_url;
    } catch (connectError) {
      setError(
        connectError instanceof Error ? connectError.message : 'Could not reach Google.',
      );
      setIsConnecting(false);
    }
  }

  async function unlinkGoogle() {
    setError(null);
    setConnectionMessage(null);
    setIsDisconnecting(true);
    try {
      await disconnectGoogle();
      setConnections((current) => current.filter((row) => row.provider !== 'google'));
      setConnectionMessage('Google Calendar disconnected.');
    } catch (disconnectError) {
      setError(
        disconnectError instanceof Error ? disconnectError.message : 'Could not disconnect Google.',
      );
    } finally {
      setIsDisconnecting(false);
    }
  }

  const upcomingBlocks = useMemo(() => {
    const now = Date.now();
    return blocks
      .filter((block) => new Date(block.end_at).getTime() >= now)
      .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime());
  }, [blocks]);

  function addWindow(day: AvailabilityWeekday) {
    setHours((current) => ({
      ...current,
      [day]: [...current[day], { start: '09:00', end: '17:00' }],
    }));
  }

  function updateWindow(
    day: AvailabilityWeekday,
    index: number,
    patch: Partial<{ start: string; end: string }>,
  ) {
    setHours((current) => {
      const next = [...current[day]];
      next[index] = { ...next[index], ...patch };
      return { ...current, [day]: next };
    });
  }

  function removeWindow(day: AvailabilityWeekday, index: number) {
    setHours((current) => ({
      ...current,
      [day]: current[day].filter((_, position) => position !== index),
    }));
  }

  async function saveRules() {
    setError(null);
    setSavedRulesAt(null);
    setIsSavingRules(true);
    try {
      await upsertAvailabilityRule({ timezone, weekly_hours: hours });
      setSavedRulesAt(new Date().toISOString());
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save your hours.');
    } finally {
      setIsSavingRules(false);
    }
  }

  async function submitBlock() {
    if (!blockStart || !blockEnd) {
      setError('A block needs both a start and an end.');
      return;
    }
    setError(null);
    setIsCreatingBlock(true);
    try {
      const created = await createAvailabilityBlock({
        start_at: isoFromLocal(blockStart),
        end_at: isoFromLocal(blockEnd),
        type: blockType,
      });
      setBlocks((current) => [...current, created]);
      setBlockStart('');
      setBlockEnd('');
    } catch (blockError) {
      setError(blockError instanceof Error ? blockError.message : 'Could not add that block.');
    } finally {
      setIsCreatingBlock(false);
    }
  }

  async function removeBlock(blockId: string) {
    setError(null);
    try {
      await deleteAvailabilityBlock(blockId);
      setBlocks((current) => current.filter((block) => block.id !== blockId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not remove that block.');
    }
  }

  if (loading) {
    return (
      <main className="wrap-narrow page" aria-busy="true">
        <div className="head">
          <div className="skel" style={{ height: '2.5rem', width: '50%' }} />
          <div className="skel" style={{ height: '1rem', width: '70%' }} />
        </div>
        <div className="skel" style={{ height: '8rem', borderRadius: '16px' }} />
        <div className="skel" style={{ height: '20rem', borderRadius: '16px' }} />
        <span className="sr-only">Loading availability</span>
      </main>
    );
  }

  return (
    <main className="wrap-narrow page">
      <div className="head reveal">
        <h1 className="title-page">Availability</h1>
        <p className="lede">
          This is what &ldquo;Find for me&rdquo; searches when it picks times on your behalf.
        </p>
      </div>

      {error ? (
        <p className="note" data-tone="bad" role="alert">
          {error}
        </p>
      ) : null}

      <section className="card reveal" style={{ ['--i' as string]: 1 }}>
        <div className="row-between">
          <div className="stack-tight">
            <span className="label">Google Calendar</span>
            <h2 className="title-card">
              {googleConnection
                ? googleConnection.provider_email ?? googleConnection.provider_account_id
                : 'Not connected'}
            </h2>
          </div>
          {googleConnection ? (
            <button
              type="button"
              className="btn btn-quiet btn-small"
              disabled={isDisconnecting}
              onClick={unlinkGoogle}
            >
              {isDisconnecting ? 'Disconnecting…' : 'Disconnect'}
            </button>
          ) : (
            <button type="button" className="btn" disabled={isConnecting} onClick={connectGoogle}>
              {isConnecting ? 'Opening Google…' : 'Connect Google'}
            </button>
          )}
        </div>
        <p className="note" data-tone="info">
          SYZY reads when you&rsquo;re busy, never event titles, guests, or notes. Connecting lets it
          skip times that clash with something already on your calendar. Disconnecting deletes the
          access token straight away.
        </p>
        {connectionMessage ? (
          <p className="note" data-tone="good" role="status">
            {connectionMessage}
          </p>
        ) : null}
      </section>

      <section className="card reveal" style={{ ['--i' as string]: 2 }}>
        <div className="row-between">
          <h2 className="title-card">Weekly hours</h2>
          <span className="muted">Days with no window are treated as unavailable</span>
        </div>

        <label className="field">
          <span className="field-label">Timezone</span>
          <input
            className="input"
            type="text"
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="America/New_York"
          />
        </label>

        <ul className="daylist">
          {WEEKDAYS.map(({ id, label }) => (
            <li key={id} className="dayrow">
              <div className="dayrow-head">
                <strong>{label}</strong>
                <button className="btn btn-text btn-small" type="button" onClick={() => addWindow(id)}>
                  Add hours
                </button>
              </div>
              {hours[id].length === 0 ? (
                <p className="field-hint">Unavailable</p>
              ) : (
                <ul className="stack-tight">
                  {hours[id].map((window, index) => (
                    <li key={`${id}-${index}`} className="windowrow">
                      <label className="field">
                        <span className="sr-only">{label} start</span>
                        <input
                          className="input"
                          type="time"
                          value={window.start}
                          onChange={(event) => updateWindow(id, index, { start: event.target.value })}
                        />
                      </label>
                      <span className="field-hint">to</span>
                      <label className="field">
                        <span className="sr-only">{label} end</span>
                        <input
                          className="input"
                          type="time"
                          value={window.end}
                          onChange={(event) => updateWindow(id, index, { end: event.target.value })}
                        />
                      </label>
                      <button
                        className="btn btn-danger-text"
                        type="button"
                        onClick={() => removeWindow(id, index)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>

        <div className="row">
          <button className="btn" type="button" disabled={isSavingRules} onClick={saveRules}>
            {isSavingRules ? 'Saving…' : 'Save weekly hours'}
          </button>
          {savedRulesAt ? (
            <span className="field-hint" role="status">
              Saved {formatMoment(savedRulesAt, timezone)}
            </span>
          ) : null}
        </div>
      </section>

      <section className="card reveal" style={{ ['--i' as string]: 3 }}>
        <h2 className="title-card">Block off time</h2>
        <p className="field-hint">
          Blocked time never gets offered. Anyone answering your requests just sees fewer options —
          never the reason.
        </p>

        <div className="pair">
          <label className="field">
            <span className="field-label">From</span>
            <input
              className="input"
              type="datetime-local"
              value={blockStart}
              onChange={(event) => setBlockStart(event.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Until</span>
            <input
              className="input"
              type="datetime-local"
              value={blockEnd}
              onChange={(event) => setBlockEnd(event.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Reason (private)</span>
            <select
              className="input"
              value={blockType}
              onChange={(event) => setBlockType(event.target.value as AvailabilityBlock['type'])}
            >
              <option value="private">Private</option>
              <option value="busy">Busy</option>
              <option value="ooo">Out of office</option>
            </select>
          </label>
        </div>

        <div className="row">
          <button
            className="btn btn-quiet btn-small"
            type="button"
            disabled={isCreatingBlock}
            onClick={submitBlock}
          >
            {isCreatingBlock ? 'Adding…' : 'Add block'}
          </button>
        </div>

        {upcomingBlocks.length === 0 ? (
          <p className="field-hint">Nothing blocked ahead.</p>
        ) : (
          <ul className="people">
            {upcomingBlocks.map((block) => (
              <li className="person" key={block.id}>
                <span className="dot" data-tone="out" />
                <span className="person-name">
                  <strong>{BLOCK_LABEL[block.type]}</strong>
                  <span>
                    {formatMoment(block.start_at, timezone)} → {formatMoment(block.end_at, timezone)}
                  </span>
                </span>
                <button
                  className="btn btn-danger-text"
                  type="button"
                  onClick={() => removeBlock(block.id)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
