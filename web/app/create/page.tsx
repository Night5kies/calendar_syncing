'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import {
  addParticipant,
  addProposal,
  createRequest,
  createShareLink,
} from '../../lib/api';
import type { RequestTemplate } from '../../lib/types';

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

  const durationTouched = useRef(false);
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

    if (options.length < 3 || options.some((option) => !option.start)) {
      setError('Add 3 to 5 time options for the MVP poll.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      const request = await createRequest({
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

      for (const participant of parsedParticipants) {
        await addParticipant(request.id, {
          display_name: participant.displayName,
          email: participant.email,
          phone: participant.phone,
        });
      }

      for (const [index, option] of options.entries()) {
        await addProposal(request.id, {
          rank: index + 1,
          start_at: new Date(option.start).toISOString(),
        });
      }

      await createShareLink(request.id);
      persistLastSettings();
      router.push(`/request/${request.id}`);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error ? submissionError.message : 'Unable to create request.',
      );
    } finally {
      setIsSubmitting(false);
    }
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
              <p className="section-label">Manual poll</p>
              <h2>Time options</h2>
            </div>
            <div className="button-group">
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
        </section>

        {error ? <p className="error-text">{error}</p> : null}

        <button className="button button-primary" disabled={isSubmitting} type="submit">
          {isSubmitting ? 'Creating...' : 'Create request'}
        </button>
      </form>
    </main>
  );
}
