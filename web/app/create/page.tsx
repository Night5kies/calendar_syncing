'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

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

const templates: RequestTemplate[] = ['meal', 'coffee', 'study', 'hangout'];

function defaultOption(offsetDays: number, hour: number) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  date.setHours(hour, 0, 0, 0);
  return date.toISOString().slice(0, 16);
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
  const [durationMinutes, setDurationMinutes] = useState(90);
  const [timezone, setTimezone] = useState('America/New_York');
  const [notes, setNotes] = useState('');
  const [responseDeadline, setResponseDeadline] = useState(defaultOption(1, 21));
  const [remindersEnabled, setRemindersEnabled] = useState(true);
  const [participants, setParticipants] = useState(
    'Alex | alex@example.com\nJules | 555-222-0101\nMaya | maya@example.com',
  );
  const [options, setOptions] = useState<OptionForm[]>([
    { id: 'o1', start: defaultOption(2, 18) },
    { id: 'o2', start: defaultOption(3, 19) },
    { id: 'o3', start: defaultOption(5, 17) },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canAddOption = options.length < 5;

  function updateOption(id: string, start: string) {
    setOptions((current) =>
      current.map((option) => (option.id === id ? { ...option, start } : option)),
    );
  }

  function addOption() {
    if (!canAddOption) {
      return;
    }
    setOptions((current) => [
      ...current,
      {
        id: `o${current.length + 1}`,
        start: defaultOption(current.length + 2, 18),
      },
    ]);
  }

  function removeOption(id: string) {
    setOptions((current) => current.filter((option) => option.id !== id));
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
          This is now wired to the FastAPI backend. The local organizer auth path is enabled in
          backend local mode.
        </p>
      </div>

      <form className="stack-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>

        <div className="field-grid">
          <label className="field">
            <span>Template</span>
            <select
              value={template}
              onChange={(event) => setTemplate(event.target.value as RequestTemplate)}
            >
              {templates.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Duration</span>
            <select
              value={durationMinutes}
              onChange={(event) => setDurationMinutes(Number(event.target.value))}
            >
              {[30, 45, 60, 90].map((value) => (
                <option key={value} value={value}>
                  {value} min
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="field">
          <span>Timezone</span>
          <input
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="America/New_York"
          />
        </label>

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
          <p className="helper-copy">Backend rule: 3 to 5 manual options, locked after send.</p>
        </section>

        {error ? <p className="error-text">{error}</p> : null}

        <button className="button button-primary" disabled={isSubmitting} type="submit">
          {isSubmitting ? 'Creating...' : 'Create request'}
        </button>
      </form>
    </main>
  );
}
