'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import {
  addParticipant,
  addProposal,
  createRequest,
  createShareLink,
  suggestProposals,
  type SuggestSlotPayload,
} from '../../lib/api';
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
    helper: 'Lunch + dinner windows, 75 min',
    durationMin: 75,
    slotHours: [19, 19, 12],
  },
  coffee: {
    label: 'Coffee',
    helper: 'Morning + afternoon, 30 min',
    durationMin: 30,
    slotHours: [9, 15, 10],
  },
  study: {
    label: 'Study',
    helper: 'Late afternoon + evening, 60 min',
    durationMin: 60,
    slotHours: [17, 19, 20],
  },
  hangout: {
    label: 'Hangout',
    helper: 'Afternoon + evening, 90 min',
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

export default function CreatePage() {
  const router = useRouter();
  const [title, setTitle] = useState('Dinner next week');
  const [template, setTemplate] = useState<RequestTemplate>('meal');
  const [durationMinutes, setDurationMinutes] = useState(TEMPLATE_CONFIG.meal.durationMin);
  const [timezone, setTimezone] = useState('America/New_York');
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
  const [slotsTouched, setSlotsTouched] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    setHasSavedSettings(window.localStorage.getItem(LAST_SETTINGS_KEY) !== null);
  }, []);

  const canAddOption = options.length < 5;

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
      throw new Error('Time-of-day window: end must be after start.');
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

  async function previewAutoSuggestions() {
    setError(null);
    setAutoPreview(null);
    setIsPreviewing(true);
    try {
      const constraints = autoConstraintsPayload();
      // Preview requires an existing request id; create a throwaway draft, preview, delete.
      // Cheaper path: re-use a single draft created at preview time and keep it for submit.
      const created = await createRequest({
        title,
        duration_min: durationMinutes,
        timezone,
        event_type: template,
        location: location.trim() || null,
        video_link: videoLink.trim() || null,
        notes: notes || null,
        response_deadline: responseDeadline ? new Date(responseDeadline).toISOString() : null,
        reminders_enabled: remindersEnabled,
      });
      const result = await suggestProposals(created.id, { ...constraints, mode: 'preview' });
      setAutoPreview(result.suggestions);
      // store the draft id so submit can finalize against the same one
      previewDraftIdRef.current = created.id;
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : 'Unable to preview suggestions.');
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const parsedParticipants = participants
      .split('\n')
      .map(parseParticipantLine)
      .filter((entry): entry is ParsedParticipant => entry !== null);

    if (parsedParticipants.length === 0) {
      setError('Add at least one participant.');
      return;
    }

    if (
      parsedParticipants.some(
        (participant) => !participant.displayName || (!participant.email && !participant.phone),
      )
    ) {
      setError('Each participant line must include a name and either an email or phone.');
      return;
    }

    if (pollMode === 'manual' && (options.length < 3 || options.some((option) => !option.start))) {
      setError('Add 3 to 5 time options for the MVP poll.');
      return;
    }

    if (pollMode === 'auto' && !autoStartDate) {
      setError('Pick a start date for the search range.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      let requestId = pollMode === 'auto' ? previewDraftIdRef.current : null;
      if (!requestId) {
        const created = await createRequest({
          title,
          duration_min: durationMinutes,
          timezone,
          event_type: template,
          location: location.trim() || null,
          video_link: videoLink.trim() || null,
          notes: notes || null,
          response_deadline: responseDeadline ? new Date(responseDeadline).toISOString() : null,
          reminders_enabled: remindersEnabled,
        });
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
      previewDraftIdRef.current = null;
      router.push(`/request/${requestId}`);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error ? submissionError.message : 'Unable to create request.',
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
    <main className="shell shell-narrow">
      <div className="page-head">
        <p className="eyebrow">Organizer flow</p>
        <h1>Create a request</h1>
        <p className="lede">
          Pick a template — it sets sensible defaults you can edit. Wired to the FastAPI backend via
          local dev auth.
        </p>
      </div>

      <form className="stack-form" onSubmit={handleSubmit}>
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-label">Template</p>
              <h2>Pick a shape</h2>
            </div>
            {hasSavedSettings ? (
              <button
                className="button button-secondary"
                onClick={applyLastSettings}
                type="button"
              >
                Use my last settings
              </button>
            ) : null}
          </div>
          <div className="template-chip-row">
            {TEMPLATES.map((option) => {
              const config = TEMPLATE_CONFIG[option];
              const isActive = template === option;
              return (
                <button
                  className={`template-chip${isActive ? ' template-chip-active' : ''}`}
                  key={option}
                  onClick={() => chooseTemplate(option)}
                  type="button"
                  aria-pressed={isActive}
                >
                  <span className="template-chip-label">{config.label}</span>
                  <span className="template-chip-helper">{config.helper}</span>
                </button>
              );
            })}
          </div>
        </section>

        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>

        <div className="field-grid">
          <label className="field">
            <span>Duration</span>
            <select
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
            <span>Timezone</span>
            <input
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              placeholder="America/New_York"
            />
          </label>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>Location (optional)</span>
            <input
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Joe's Coffee on Main"
            />
          </label>
          <label className="field">
            <span>Video link (optional)</span>
            <input
              value={videoLink}
              onChange={(event) => setVideoLink(event.target.value)}
              placeholder="https://meet.google.com/..."
              type="url"
            />
          </label>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>Response deadline</span>
            <input
              type="datetime-local"
              value={responseDeadline}
              onChange={(event) => setResponseDeadline(event.target.value)}
            />
          </label>
          <div className="field field-checkbox">
            <span>Reminder policy</span>
            <label className="checkbox-row">
              <input
                checked={remindersEnabled}
                onChange={(event) => setRemindersEnabled(event.target.checked)}
                type="checkbox"
              />
              <span>Auto-remind non-responders</span>
            </label>
          </div>
        </div>

        <label className="field">
          <span>Participants</span>
          <textarea
            rows={5}
            value={participants}
            onChange={(event) => setParticipants(event.target.value)}
            placeholder="One per line: Name | email@example.com or Name | 555-222-0101"
          />
        </label>

        <label className="field">
          <span>Notes</span>
          <textarea
            rows={4}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Optional context for the group"
          />
        </label>

        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="section-label">Poll mode</p>
              <h2>{pollMode === 'manual' ? 'Time options' : 'Find a time'}</h2>
            </div>
            <div className="mode-toggle" role="group" aria-label="Poll mode">
              <button
                className={`mode-toggle-button${pollMode === 'manual' ? ' mode-toggle-button-active' : ''}`}
                type="button"
                aria-pressed={pollMode === 'manual'}
                onClick={() => setPollMode('manual')}
              >
                Manual poll
              </button>
              <button
                className={`mode-toggle-button${pollMode === 'auto' ? ' mode-toggle-button-active' : ''}`}
                type="button"
                aria-pressed={pollMode === 'auto'}
                onClick={() => setPollMode('auto')}
              >
                Find a time
              </button>
            </div>
          </div>

          {pollMode === 'manual' ? (
            <>
              <div className="button-group" style={{ justifyContent: 'flex-end' }}>
                {slotsTouched ? (
                  <button
                    className="button button-secondary"
                    onClick={resetSlotsToTemplate}
                    type="button"
                  >
                    Reset to template
                  </button>
                ) : null}
                <button className="button button-secondary" onClick={addOption} type="button">
                  Add option
                </button>
              </div>
              <div className="option-list">
                {options.map((option, index) => (
                  <div className="option-row" key={option.id}>
                    <label className="field">
                      <span>Option {index + 1}</span>
                      <input
                        type="datetime-local"
                        value={option.start}
                        onChange={(event) => updateOption(option.id, event.target.value)}
                      />
                    </label>
                    <button
                      className="inline-link"
                      onClick={() => removeOption(option.id)}
                      type="button"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <p className="helper-copy">
                Backend rule: 3 to 5 manual options, locked after send. Template pre-fills sensible
                windows you can edit.
              </p>
            </>
          ) : (
            <>
              <p className="helper-copy">
                We&rsquo;ll pick {autoSuggestionLimit} slots inside your constraints and the
                organizer&rsquo;s saved availability. Each suggestion includes a one-line reason.
              </p>
              <div className="field-grid">
                <label className="field">
                  <span>Start date</span>
                  <input
                    type="date"
                    value={autoStartDate}
                    onChange={(event) => setAutoStartDate(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>End date</span>
                  <input
                    type="date"
                    value={autoEndDate}
                    onChange={(event) => setAutoEndDate(event.target.value)}
                  />
                </label>
              </div>
              <div className="field">
                <span>Days of week</span>
                <div className="weekday-chip-row">
                  {WEEKDAY_CHIPS.map((day) => {
                    const isActive = autoWeekdays.includes(day.value);
                    return (
                      <button
                        key={day.value}
                        type="button"
                        className={`weekday-chip${isActive ? ' weekday-chip-active' : ''}`}
                        aria-pressed={isActive}
                        onClick={() => toggleWeekday(day.value)}
                      >
                        {day.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="field-grid">
                <label className="field">
                  <span>Earliest start (local)</span>
                  <input
                    type="time"
                    value={autoWindowStart}
                    onChange={(event) => setAutoWindowStart(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Latest end (local)</span>
                  <input
                    type="time"
                    value={autoWindowEnd}
                    onChange={(event) => setAutoWindowEnd(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>How many suggestions</span>
                  <input
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
                <span>Exclude dates (comma-separated, YYYY-MM-DD)</span>
                <input
                  type="text"
                  value={autoExcludes}
                  placeholder="2026-05-30, 2026-06-01"
                  onChange={(event) => setAutoExcludes(event.target.value)}
                />
              </label>
              <div className="button-group">
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={isPreviewing}
                  onClick={previewAutoSuggestions}
                >
                  {isPreviewing ? 'Searching…' : 'Preview suggestions'}
                </button>
              </div>
              {autoPreview ? (
                autoPreview.length === 0 ? (
                  <p className="helper-copy">No slots match those constraints. Widen the window or add days.</p>
                ) : (
                  <ul className="suggestion-list">
                    {autoPreview.map((slot, index) => (
                      <li key={slot.start_at + index} className="suggestion-item">
                        <strong>
                          {new Date(slot.start_at).toLocaleString(undefined, { timeZone: timezone })}
                        </strong>
                        <span className="helper-copy">
                          {slot.reasons.join(' · ')} · score {slot.score.toFixed(2)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )
              ) : null}
            </>
          )}
        </section>

        {error ? <p className="error-text">{error}</p> : null}

        <button className="button button-primary" disabled={isSubmitting} type="submit">
          {isSubmitting ? 'Creating...' : 'Create request'}
        </button>
      </form>
    </main>
  );
}
