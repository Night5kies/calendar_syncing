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
import { formatDateTime } from '../../../lib/types';

const WEEKDAYS: { id: AvailabilityWeekday; label: string }[] = [
  { id: 'mon', label: 'Mon' },
  { id: 'tue', label: 'Tue' },
  { id: 'wed', label: 'Wed' },
  { id: 'thu', label: 'Thu' },
  { id: 'fri', label: 'Fri' },
  { id: 'sat', label: 'Sat' },
  { id: 'sun', label: 'Sun' },
];

function emptyHours(): AvailabilityWeeklyHours {
  return {
    mon: [],
    tue: [],
    wed: [],
    thu: [],
    fri: [],
    sat: [],
    sun: [],
  };
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

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
  } catch {
    return 'America/New_York';
  }
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
          setError(loadError instanceof Error ? loadError.message : 'Unable to load availability.');
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
        connectError instanceof Error
          ? connectError.message
          : 'Unable to start Google connect flow.',
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
        disconnectError instanceof Error
          ? disconnectError.message
          : 'Unable to disconnect Google.',
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
      setError(saveError instanceof Error ? saveError.message : 'Unable to save availability.');
    } finally {
      setIsSavingRules(false);
    }
  }

  async function submitBlock() {
    if (!blockStart || !blockEnd) {
      setError('Pick a start and end time for the block.');
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
      setError(blockError instanceof Error ? blockError.message : 'Unable to create block.');
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
      setError(deleteError instanceof Error ? deleteError.message : 'Unable to delete block.');
    }
  }

  if (loading) {
    return (
      <main className="shell shell-narrow">
        <div className="page-head">
          <p className="eyebrow">Settings</p>
          <h1>Loading availability…</h1>
        </div>
      </main>
    );
  }

  return (
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Settings</p>
        <h1>Availability</h1>
        <p className="lede">
          Set your working hours and block off times that should never appear as suggestions.
        </p>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="section-label">Google Calendar</p>
            <h2>
              {googleConnection
                ? `Connected to ${googleConnection.provider_email ?? googleConnection.provider_account_id}`
                : 'Connect your calendar'}
            </h2>
          </div>
          {googleConnection ? (
            <button
              type="button"
              className="button button-secondary"
              disabled={isDisconnecting}
              onClick={unlinkGoogle}
            >
              {isDisconnecting ? 'Disconnecting…' : 'Disconnect'}
            </button>
          ) : (
            <button
              type="button"
              className="button button-primary"
              disabled={isConnecting}
              onClick={connectGoogle}
            >
              {isConnecting ? 'Redirecting…' : 'Connect Google'}
            </button>
          )}
        </div>
        <p className="helper-copy privacy-copy">
          SYZY reads when you’re busy, never event titles. Connecting lets the “Find a time” flow skip
          slots that overlap an existing meeting. Disconnecting deletes the access token immediately.
        </p>
        {connectionMessage ? <p className="success-text">{connectionMessage}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="section-label">Weekly hours</p>
            <h2>When you’re generally free</h2>
          </div>
        </div>
        <label className="field">
          <span>Timezone</span>
          <input
            type="text"
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="America/New_York"
          />
        </label>
        <div className="availability-grid">
          {WEEKDAYS.map(({ id, label }) => (
            <div key={id} className="availability-day">
              <div className="availability-day-head">
                <strong>{label}</strong>
                <button
                  className="button button-ghost"
                  type="button"
                  onClick={() => addWindow(id)}
                >
                  + Add window
                </button>
              </div>
              {hours[id].length === 0 ? (
                <p className="helper-copy">Unavailable</p>
              ) : (
                <ul className="availability-window-list">
                  {hours[id].map((window, index) => (
                    <li key={`${id}-${index}`} className="availability-window">
                      <label className="field">
                        <span>Start</span>
                        <input
                          type="time"
                          value={window.start}
                          onChange={(event) =>
                            updateWindow(id, index, { start: event.target.value })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>End</span>
                        <input
                          type="time"
                          value={window.end}
                          onChange={(event) =>
                            updateWindow(id, index, { end: event.target.value })
                          }
                        />
                      </label>
                      <button
                        className="button button-ghost"
                        type="button"
                        onClick={() => removeWindow(id, index)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
        <div className="button-group">
          <button
            className="button button-primary"
            type="button"
            disabled={isSavingRules}
            onClick={saveRules}
          >
            {isSavingRules ? 'Saving…' : 'Save weekly hours'}
          </button>
        </div>
        {savedRulesAt ? (
          <p className="success-text">Saved at {formatDateTime(savedRulesAt, timezone)}</p>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="section-label">One-off blocks</p>
            <h2>Block times that should never be suggested</h2>
          </div>
        </div>
        <p className="helper-copy">
          Blocks are private. Anyone responding to your meeting requests only sees that a time isn’t
          offered — never the title or reason.
        </p>
        <div className="field-grid">
          <label className="field">
            <span>Start</span>
            <input
              type="datetime-local"
              value={blockStart}
              onChange={(event) => setBlockStart(event.target.value)}
            />
          </label>
          <label className="field">
            <span>End</span>
            <input
              type="datetime-local"
              value={blockEnd}
              onChange={(event) => setBlockEnd(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Type</span>
            <select
              value={blockType}
              onChange={(event) => setBlockType(event.target.value as AvailabilityBlock['type'])}
            >
              <option value="private">Private</option>
              <option value="busy">Busy</option>
              <option value="ooo">Out of office</option>
            </select>
          </label>
        </div>
        <div className="button-group">
          <button
            className="button button-secondary"
            type="button"
            disabled={isCreatingBlock}
            onClick={submitBlock}
          >
            {isCreatingBlock ? 'Adding…' : 'Add block'}
          </button>
        </div>

        {upcomingBlocks.length === 0 ? (
          <p className="helper-copy">No upcoming blocks.</p>
        ) : (
          <ul className="availability-block-list">
            {upcomingBlocks.map((block) => (
              <li key={block.id} className="availability-block-item">
                <div>
                  <strong>{block.type}</strong>
                  <p className="helper-copy">
                    {formatDateTime(block.start_at, timezone)} →{' '}
                    {formatDateTime(block.end_at, timezone)}
                  </p>
                </div>
                <button
                  className="button button-ghost"
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
