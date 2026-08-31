'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  addParticipant,
  addProposal,
  createRequest,
  createShareLink,
  suggestProposals,
  type SuggestSlotPayload,
} from '../../lib/api';
import { rememberRequest } from '../../lib/recents';
import { browserTimezone, formatMoment, shapeSlot } from '../../lib/time';
import type { RequestTemplate } from '../../lib/types';

type PollMode = 'manual' | 'auto';

const WEEKDAY_CHIPS: { value: number; label: string }[] = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
];

function isoDateOnly(offsetDays: number): string {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + offsetDays);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function timeStringToMinutes(value: string): number {
  const [hours, minutes] = value.split(':').map((part) => Number(part));
  return Math.max(0, Math.min(1440, hours * 60 + minutes));
}

type OptionForm = {
  id: string;
  start: string;
};

type ParsedParticipant = {
  displayName: string;
  email?: string;
  phone?: string;
};

type TemplateConfig = {
  label: string;
  helper: string;
  durationMin: number;
  slotHours: number[];
};

const TEMPLATE_CONFIG: Record<RequestTemplate, TemplateConfig> = {
  meal: {
    label: 'Meal',
    helper: 'Two dinners and a lunch',
    durationMin: 75,
    slotHours: [19, 19, 12],
  },
  coffee: {
    label: 'Coffee',
    helper: 'Mornings and one afternoon',
    durationMin: 30,
    slotHours: [9, 15, 10],
  },
  study: {
    label: 'Study',
    helper: 'Late afternoons and evenings',
    durationMin: 60,
    slotHours: [17, 19, 20],
  },
  hangout: {
    label: 'Hangout',
    helper: 'Afternoons and evenings',
    durationMin: 90,
    slotHours: [15, 19, 19],
  },
};

const TEMPLATES: RequestTemplate[] = ['meal', 'coffee', 'study', 'hangout'];

const LAST_SETTINGS_KEY = 'syzy:last-create-settings';

type LastSettings = {
  template: RequestTemplate;
  durationMinutes: number;
  timezone: string;
  remindersEnabled: boolean;
  location: string;
  videoLink: string;
  notes: string;
};

function defaultOption(offsetDays: number, hour: number) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  date.setHours(hour, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function slotsForTemplate(template: RequestTemplate): OptionForm[] {
  const { slotHours } = TEMPLATE_CONFIG[template];
  return slotHours.map((hour, index) => ({
    id: `o${index + 1}`,
    start: defaultOption(index + 2, hour),
  }));
}

function looksLikeEmail(value: string) {
  return value.includes('@');
}

function parseParticipantLine(line: string): ParsedParticipant | null {
  const trimmed = line.trim();
  if (!trimmed) {
    return null;
  }

  const parts = trimmed.split('|').map((part) => part.trim()).filter(Boolean);
  if (parts.length === 1) {
    const only = parts[0];
    if (looksLikeEmail(only)) {
      return { displayName: only.split('@')[0], email: only.toLowerCase() };
    }
    return { displayName: only, phone: only };
  }

  const [displayName, contact] = parts;
  if (!displayName || !contact) {
    return null;
  }

  if (looksLikeEmail(contact)) {
    return { displayName, email: contact.toLowerCase() };
  }

  return { displayName, phone: contact };
}

/** Local `datetime-local` value -> the rail position of that moment. */
function trackStyle(localValue: string) {
  if (!localValue) return null;
  const start = new Date(localValue);
  if (Number.isNaN(start.getTime())) return null;
  const shape = shapeSlot(start.toISOString(), start.toISOString(), browserTimezone());
  return { from: shape.from, weekday: shape.weekday, day: shape.day };
}

export default function CreatePage() {
  const router = useRouter();
  const [title, setTitle] = useState('Dinner next week');
  const [template, setTemplate] = useState<RequestTemplate>('meal');
  const [durationMinutes, setDurationMinutes] = useState(TEMPLATE_CONFIG.meal.durationMin);
  const [timezone, setTimezone] = useState('America/New_York');
  const [zoneOptions, setZoneOptions] = useState<string[]>([]);
  const [notes, setNotes] = useState('');
  const [location, setLocation] = useState('');
  const [videoLink, setVideoLink] = useState('');
  const [responseDeadline, setResponseDeadline] = useState(defaultOption(1, 21));
  const [remindersEnabled, setRemindersEnabled] = useState(true);
  const [participants, setParticipants] = useState(
    'Alex | alex@example.com\nJules | 555-222-0101\nMaya | maya@example.com',
  );
  const [options, setOptions] = useState<OptionForm[]>(() => slotsForTemplate('meal'));
  const [hasSavedSettings, setHasSavedSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [pollMode, setPollMode] = useState<PollMode>('manual');
  const [autoStartDate, setAutoStartDate] = useState(() => isoDateOnly(1));
  const [autoEndDate, setAutoEndDate] = useState(() => isoDateOnly(7));
  const [autoWeekdays, setAutoWeekdays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [autoWindowStart, setAutoWindowStart] = useState('09:00');
  const [autoWindowEnd, setAutoWindowEnd] = useState('17:00');
  const [autoExcludes, setAutoExcludes] = useState('');
  const [autoSuggestionLimit, setAutoSuggestionLimit] = useState(5);
  const [autoPreview, setAutoPreview] = useState<SuggestSlotPayload[] | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const durationTouched = useRef(false);
  const previewDraftIdRef = useRef<string | null>(null);
  const previewDraftSigRef = useRef<string | null>(null);
  const [slotsTouched, setSlotsTouched] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    setHasSavedSettings(window.localStorage.getItem(LAST_SETTINGS_KEY) !== null);
    setTimezone((current) => (current === 'America/New_York' ? browserTimezone() : current));
    try {
      const supported = (
        Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
      ).supportedValuesOf?.('timeZone');
      if (supported) setZoneOptions(supported);
    } catch {
      // datalist is a convenience; the field still accepts any zone
    }
  }, []);

  const canAddOption = options.length < 5;

  const parsedParticipants = useMemo(
    () =>
      participants
        .split('\n')
        .map(parseParticipantLine)
        .filter((entry): entry is ParsedParticipant => entry !== null),
    [participants],
  );

  /**
   * "Find a time" needs a saved request before it can search, so previewing
   * creates a draft. Reuse that draft on submit only while the details it was
   * created with still match — otherwise the request would keep a stale title.
   */
  const draftSignature = [
    title,
    durationMinutes,
    timezone,
    template,
    location,
    videoLink,
    notes,
    responseDeadline,
    remindersEnabled,
  ].join('');

  function chooseTemplate(next: RequestTemplate) {
    setTemplate(next);
    const config = TEMPLATE_CONFIG[next];
    if (!durationTouched.current) {
      setDurationMinutes(config.durationMin);
    }
    if (!slotsTouched) {
      setOptions(slotsForTemplate(next));
    }
  }

  function updateOption(id: string, start: string) {
    setSlotsTouched(true);
    setOptions((current) =>
      current.map((option) => (option.id === id ? { ...option, start } : option)),
    );
  }

  function addOption() {
    if (!canAddOption) {
      return;
    }
    setSlotsTouched(true);
    setOptions((current) => [
      ...current,
      {
        id: `o${current.length + 1}`,
        start: defaultOption(current.length + 2, TEMPLATE_CONFIG[template].slotHours[0]),
      },
    ]);
  }

  function removeOption(id: string) {
    setSlotsTouched(true);
    setOptions((current) => current.filter((option) => option.id !== id));
  }

  function resetSlotsToTemplate() {
    setSlotsTouched(false);
    setOptions(slotsForTemplate(template));
  }

  function applyLastSettings() {
    if (typeof window === 'undefined') {
      return;
    }
    const raw = window.localStorage.getItem(LAST_SETTINGS_KEY);
    if (!raw) {
      return;
    }
    try {
      const saved = JSON.parse(raw) as LastSettings;
      setTemplate(saved.template);
      setDurationMinutes(saved.durationMinutes);
      setTimezone(saved.timezone);
      setRemindersEnabled(saved.remindersEnabled);
      setLocation(saved.location);
      setVideoLink(saved.videoLink);
      setNotes(saved.notes);
      durationTouched.current = true;
      if (!slotsTouched) {
        setOptions(slotsForTemplate(saved.template));
      }
    } catch {
      // ignore malformed saved settings
    }
  }

  function persistLastSettings() {
    if (typeof window === 'undefined') {
      return;
    }
    const payload: LastSettings = {
      template,
      durationMinutes,
      timezone,
      remindersEnabled,
      location,
      videoLink,
      notes,
    };
    window.localStorage.setItem(LAST_SETTINGS_KEY, JSON.stringify(payload));
  }

  function autoConstraintsPayload() {
    const startMin = timeStringToMinutes(autoWindowStart);
    const endMin = timeStringToMinutes(autoWindowEnd);
    if (endMin <= startMin) {
      throw new Error('The latest end has to come after the earliest start.');
    }
    return {
      start_date: autoStartDate,
      end_date: autoEndDate,
      days_of_week: autoWeekdays.length > 0 ? autoWeekdays : undefined,
      time_windows: [{ start_minute: startMin, end_minute: endMin }],
      exclude_dates: autoExcludes
        .split(/[\s,]+/)
        .map((token) => token.trim())
        .filter(Boolean),
      limit: autoSuggestionLimit,
    };
  }

  function newRequestPayload() {
    return {
      title,
      duration_min: durationMinutes,
      timezone,
      event_type: template,
      location: location.trim() || null,
      video_link: videoLink.trim() || null,
      notes: notes || null,
      response_deadline: responseDeadline ? new Date(responseDeadline).toISOString() : null,
      reminders_enabled: remindersEnabled,
    };
  }

  async function previewAutoSuggestions() {
    setError(null);
    setAutoPreview(null);
    setIsPreviewing(true);
    try {
      const constraints = autoConstraintsPayload();
      let draftId = previewDraftIdRef.current;
      if (!draftId || previewDraftSigRef.current !== draftSignature) {
        const created = await createRequest(newRequestPayload());
        draftId = created.id;
        previewDraftIdRef.current = draftId;
        previewDraftSigRef.current = draftSignature;
      }
      const result = await suggestProposals(draftId, { ...constraints, mode: 'preview' });
      setAutoPreview(result.suggestions);
    } catch (previewError) {
      setError(
        previewError instanceof Error ? previewError.message : 'Could not search for times.',
      );
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (parsedParticipants.length === 0) {
      setError('Add at least one person, one per line.');
      return;
    }

    if (
      parsedParticipants.some(
        (participant) => !participant.displayName || (!participant.email && !participant.phone),
      )
    ) {
      setError('Every line needs a name and either an email or a phone number.');
      return;
    }

    if (pollMode === 'manual' && (options.length < 3 || options.some((option) => !option.start))) {
      setError('Put up 3 to 5 times so people have a real choice.');
      return;
    }

    if (pollMode === 'auto' && !autoStartDate) {
      setError('Pick the first date SYZY should search from.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      let requestId =
        pollMode === 'auto' && previewDraftSigRef.current === draftSignature
          ? previewDraftIdRef.current
          : null;
      if (!requestId) {
        const created = await createRequest(newRequestPayload());
        requestId = created.id;
      }

      for (const participant of parsedParticipants) {
        await addParticipant(requestId, {
          display_name: participant.displayName,
          email: participant.email,
          phone: participant.phone,
        });
      }

      if (pollMode === 'manual') {
        for (const [index, option] of options.entries()) {
          await addProposal(requestId, {
            rank: index + 1,
            start_at: new Date(option.start).toISOString(),
          });
        }
      } else {
        const constraints = autoConstraintsPayload();
        await suggestProposals(requestId, {
          ...constraints,
          mode: 'suggest',
          replace_existing: true,
        });
      }

      await createShareLink(requestId);
      persistLastSettings();
      rememberRequest({ id: requestId, title, createdAt: new Date().toISOString() });
      previewDraftIdRef.current = null;
      previewDraftSigRef.current = null;
      router.push(`/request/${requestId}`);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error ? submissionError.message : 'Could not create the request.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function toggleWeekday(value: number) {
    setAutoWeekdays((current) =>
      current.includes(value)
        ? current.filter((day) => day !== value)
        : [...current, value].sort((a, b) => a - b),
    );
  }

  return (
    <main className="wrap-narrow page">
      <div className="head reveal">
        <h1 className="title-page">New request</h1>
        <p className="lede">
          Put a few times on the table, then send one link to the group. You can change everything
          up until you send it.
        </p>
      </div>

      <form className="stack-loose" onSubmit={handleSubmit}>
        <section className="card reveal" style={{ ['--i' as string]: 1 }}>
          <div className="row-between">
            <h2 className="title-card">The plan</h2>
            {hasSavedSettings ? (
              <button className="btn btn-text btn-small" onClick={applyLastSettings} type="button">
                Use my last settings
              </button>
            ) : null}
          </div>

          <div className="chips-grid">
            {TEMPLATES.map((option) => {
              const config = TEMPLATE_CONFIG[option];
              return (
                <button
                  className="chip chip-tall"
                  key={option}
                  onClick={() => chooseTemplate(option)}
                  type="button"
                  aria-pressed={template === option}
                >
                  <strong>{config.label}</strong>
                  <span>{config.helper}</span>
                </button>
              );
            })}
          </div>

          <label className="field">
            <span className="field-label">What are you calling it?</span>
            <input
              className="input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Dinner next week"
            />
          </label>

          <div className="pair">
            <label className="field">
              <span className="field-label">How long</span>
              <select
                className="input"
                value={durationMinutes}
                onChange={(event) => {
                  durationTouched.current = true;
                  setDurationMinutes(Number(event.target.value));
                }}
              >
                {[15, 30, 45, 60, 75, 90, 120].map((value) => (
                  <option key={value} value={value}>
                    {value} min
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Timezone</span>
              <input
                className="input"
                list="syzy-timezones"
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
                placeholder="America/New_York"
              />
              <datalist id="syzy-timezones">
                {zoneOptions.map((zone) => (
                  <option key={zone} value={zone} />
                ))}
              </datalist>
            </label>
          </div>

          <div className="pair">
            <label className="field">
              <span className="field-label">Where (optional)</span>
              <input
                className="input"
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="Joe's on Main"
              />
            </label>
            <label className="field">
              <span className="field-label">Video link (optional)</span>
              <input
                className="input"
                value={videoLink}
                onChange={(event) => setVideoLink(event.target.value)}
                placeholder="https://meet.google.com/..."
                type="url"
              />
            </label>
          </div>

          <label className="field">
            <span className="field-label">Anything they should know (optional)</span>
            <textarea
              className="input"
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Booking a table for six, so I need a headcount by Friday."
            />
          </label>
        </section>

        <section className="card reveal" style={{ ['--i' as string]: 2 }}>
          <div className="row-between">
            <h2 className="title-card">{pollMode === 'manual' ? 'The times' : 'Find a time'}</h2>
            <div className="segmented" role="group" aria-label="How to choose times">
              <button
                type="button"
                aria-pressed={pollMode === 'manual'}
                onClick={() => setPollMode('manual')}
              >
                I&rsquo;ll pick
              </button>
              <button
                type="button"
                aria-pressed={pollMode === 'auto'}
                onClick={() => setPollMode('auto')}
              >
                Find for me
              </button>
            </div>
          </div>

          {pollMode === 'manual' ? (
            <>
              <p className="field-hint">
                Three to five options. They lock once you send, so a change after that means
                starting a new request.
              </p>
              <ul className="optlist">
                {options.map((option, index) => {
                  const track = trackStyle(option.start);
                  return (
                    <li className="optrow" key={option.id}>
                      <div className="optrow-main">
                        <label className="field grow">
                          <span className="field-label">Option {index + 1}</span>
                          <input
                            className="input"
                            type="datetime-local"
                            value={option.start}
                            onChange={(event) => updateOption(option.id, event.target.value)}
                          />
                        </label>
                        <button
                          className="btn btn-danger-text"
                          onClick={() => removeOption(option.id)}
                          type="button"
                          disabled={options.length <= 1}
                        >
                          Remove
                        </button>
                      </div>
                      {track ? (
                        <div className="optrow-track">
                          <span className="optrow-day">
                            {track.weekday} {track.day}
                          </span>
                          <span className="track">
                            <span className="track-noon" />
                            <span
                              className="track-fill"
                              style={{
                                ['--from' as string]: `${track.from}%`,
                                ['--span' as string]: `${Math.max(
                                  2,
                                  (durationMinutes / (18 * 60)) * 100,
                                )}%`,
                              }}
                            />
                          </span>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <div className="row">
                <button
                  className="btn btn-quiet btn-small"
                  onClick={addOption}
                  type="button"
                  disabled={!canAddOption}
                >
                  Add an option
                </button>
                {slotsTouched ? (
                  <button
                    className="btn btn-text btn-small"
                    onClick={resetSlotsToTemplate}
                    type="button"
                  >
                    Back to the {TEMPLATE_CONFIG[template].label.toLowerCase()} defaults
                  </button>
                ) : null}
                {!canAddOption ? <span className="field-hint">Five is the maximum.</span> : null}
              </div>
            </>
          ) : (
            <>
              <p className="field-hint">
                SYZY searches your saved availability and connected calendar inside these limits,
                then puts the best {autoSuggestionLimit} openings up for a vote.
              </p>
              <div className="pair">
                <label className="field">
                  <span className="field-label">Search from</span>
                  <input
                    className="input"
                    type="date"
                    value={autoStartDate}
                    onChange={(event) => setAutoStartDate(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Search until</span>
                  <input
                    className="input"
                    type="date"
                    value={autoEndDate}
                    onChange={(event) => setAutoEndDate(event.target.value)}
                  />
                </label>
              </div>
              <div className="field">
                <span className="field-label">Days that work</span>
                <div className="chips">
                  {WEEKDAY_CHIPS.map((day) => (
                    <button
                      key={day.value}
                      type="button"
                      className="chip"
                      aria-pressed={autoWeekdays.includes(day.value)}
                      onClick={() => toggleWeekday(day.value)}
                    >
                      {day.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="pair">
                <label className="field">
                  <span className="field-label">No earlier than</span>
                  <input
                    className="input"
                    type="time"
                    value={autoWindowStart}
                    onChange={(event) => setAutoWindowStart(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field-label">No later than</span>
                  <input
                    className="input"
                    type="time"
                    value={autoWindowEnd}
                    onChange={(event) => setAutoWindowEnd(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field-label">How many to offer</span>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={10}
                    value={autoSuggestionLimit}
                    onChange={(event) =>
                      setAutoSuggestionLimit(Math.max(1, Math.min(10, Number(event.target.value))))
                    }
                  />
                </label>
              </div>
              <label className="field">
                <span className="field-label">Skip these dates (optional)</span>
                <input
                  className="input"
                  type="text"
                  value={autoExcludes}
                  placeholder="2026-05-30, 2026-06-01"
                  onChange={(event) => setAutoExcludes(event.target.value)}
                />
              </label>
              <div className="row">
                <button
                  type="button"
                  className="btn btn-quiet btn-small"
                  disabled={isPreviewing}
                  onClick={previewAutoSuggestions}
                >
                  {isPreviewing ? 'Searching…' : 'Show me what it finds'}
                </button>
              </div>
              {autoPreview ? (
                autoPreview.length === 0 ? (
                  <p className="note">
                    Nothing is open inside those limits. Try widening the hours or adding a day.
                  </p>
                ) : (
                  <ul className="stack-tight">
                    {autoPreview.map((slot, index) => (
                      <li key={slot.start_at + index} className="suggestion">
                        <strong>{formatMoment(slot.start_at, timezone)}</strong>
                        <span className="field-hint">{slot.reasons.join(' · ')}</span>
                      </li>
                    ))}
                  </ul>
                )
              ) : null}
            </>
          )}
        </section>

        <section className="card reveal" style={{ ['--i' as string]: 3 }}>
          <h2 className="title-card">Who&rsquo;s coming</h2>
          <label className="field">
            <span className="field-label">One person per line</span>
            <textarea
              className="input"
              rows={5}
              value={participants}
              onChange={(event) => setParticipants(event.target.value)}
              placeholder="Alex | alex@example.com"
            />
            <span className="field-hint">
              Name, then a pipe, then an email or phone. Email gets them their own link.
            </span>
          </label>
          {parsedParticipants.length > 0 ? (
            <div className="chips" aria-live="polite">
              {parsedParticipants.map((person, index) => (
                <span className="pill pill-name" key={`${person.displayName}-${index}`}>
                  <span className="dot" data-tone={person.email ? 'in' : 'waiting'} />
                  {person.displayName}
                </span>
              ))}
            </div>
          ) : null}
        </section>

        <section className="card reveal" style={{ ['--i' as string]: 4 }}>
          <h2 className="title-card">Chasing people</h2>
          <div className="pair">
            <label className="field">
              <span className="field-label">Answers due by</span>
              <input
                className="input"
                type="datetime-local"
                value={responseDeadline}
                onChange={(event) => setResponseDeadline(event.target.value)}
              />
            </label>
            <div className="field">
              <span className="field-label">Reminders</span>
              <label className="check">
                <input
                  checked={remindersEnabled}
                  onChange={(event) => setRemindersEnabled(event.target.checked)}
                  type="checkbox"
                />
                <span>Nudge anyone who hasn&rsquo;t answered</span>
              </label>
            </div>
          </div>
        </section>

        {error ? (
          <p className="note" data-tone="bad" role="alert">
            {error}
          </p>
        ) : null}

        <button className="btn btn-wide" disabled={isSubmitting} type="submit">
          {isSubmitting ? 'Creating…' : 'Create request'}
        </button>
      </form>
    </main>
  );
}
