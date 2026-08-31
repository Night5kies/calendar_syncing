/**
 * Time formatting for the slot card — the one component that carries this
 * product's whole story (candidates in play, then one decided).
 *
 * Everything here works in an explicit IANA timezone. The organizer schedules
 * in their zone; attendees read in theirs. Never let the machine's local zone
 * leak in implicitly.
 */

const DAY_START_MIN = 6 * 60; // the rail starts at 6am
const DAY_END_MIN = 24 * 60; // and ends at midnight
const RAIL_MIN = DAY_END_MIN - DAY_START_MIN;

type Parts = {
  weekday: string;
  month: string;
  day: string;
  hour: number;
  minute: number;
};

function partsIn(iso: string, timeZone: string): Parts | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
    const found = Object.fromEntries(
      formatter.formatToParts(date).map((part) => [part.type, part.value]),
    ) as Record<string, string>;

    return {
      weekday: found.weekday ?? '',
      month: found.month ?? '',
      day: found.day ?? '',
      hour: Number(found.hour ?? '0') % 24,
      minute: Number(found.minute ?? '0'),
    };
  } catch {
    return null;
  }
}

function clockLabel(hour: number, minute: number): string {
  const suffix = hour >= 12 ? 'pm' : 'am';
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return minute === 0 ? `${display}${suffix}` : `${display}:${String(minute).padStart(2, '0')}${suffix}`;
}

export type SlotShape = {
  /** "Thu" */
  weekday: string;
  /** "12" */
  day: string;
  /** "Mar" */
  month: string;
  /** "7:00 – 8:15pm" */
  time: string;
  /** "Thursday, March 12" — for screen readers and long-form copy */
  full: string;
  /** left edge on the 6am–midnight rail, as a percentage */
  from: number;
  /** width on the rail, as a percentage */
  span: number;
};

export function shapeSlot(startIso: string, endIso: string, timeZone: string): SlotShape {
  const start = partsIn(startIso, timeZone);
  const end = partsIn(endIso, timeZone);

  if (!start) {
    return { weekday: '--', day: '--', month: '', time: 'Time unavailable', full: '', from: 0, span: 6 };
  }

  const startMin = start.hour * 60 + start.minute;
  const endMin = end ? end.hour * 60 + end.minute : startMin + 60;
  // An event that runs past midnight reads to the end of the rail.
  const closeMin = endMin > startMin ? endMin : DAY_END_MIN;

  const from = ((Math.max(startMin, DAY_START_MIN) - DAY_START_MIN) / RAIL_MIN) * 100;
  const span = ((Math.min(closeMin, DAY_END_MIN) - Math.max(startMin, DAY_START_MIN)) / RAIL_MIN) * 100;

  const sameMeridiem = end ? start.hour >= 12 === end.hour >= 12 : true;
  const startLabel =
    end && sameMeridiem
      ? clockLabel(start.hour, start.minute).replace(/(am|pm)$/, '')
      : clockLabel(start.hour, start.minute);
  const time = end ? `${startLabel} – ${clockLabel(end.hour, end.minute)}` : clockLabel(start.hour, start.minute);

  const safeFrom = Math.max(0, Math.min(98, from));

  return {
    weekday: start.weekday,
    day: start.day,
    month: start.month,
    time,
    full: `${start.weekday} ${start.month} ${start.day}, ${time}`,
    from: safeFrom,
    span: Math.max(2, Math.min(100 - safeFrom, span)),
  };
}

/** "Thu, Mar 12 at 7:00pm" — for one-line references outside a slot card. */
export function formatMoment(iso: string | null, timeZone: string): string {
  if (!iso) return 'Not set';
  const parts = partsIn(iso, timeZone);
  if (!parts) return 'Not set';
  return `${parts.weekday}, ${parts.month} ${parts.day} at ${clockLabel(parts.hour, parts.minute)}`;
}

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/** "in 3 days" / "2 hours ago" — relative wording for deadlines and nudges. */
export function relativeTime(iso: string | null): string | null {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;

  const diffMs = target - Date.now();
  const abs = Math.abs(diffMs);
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['day', 86_400_000],
    ['hour', 3_600_000],
    ['minute', 60_000],
  ];

  for (const [unit, ms] of units) {
    if (abs >= ms) return formatter.format(Math.round(diffMs / ms), unit);
  }
  return 'just now';
}

/** Minutes rendered the way a person says them: "1 hr 15 min". */
export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const hourLabel = `${hours} hr`;
  return rest === 0 ? hourLabel : `${hourLabel} ${rest} min`;
}

/** "EDT" — the short zone name people actually recognize. */
export function zoneLabel(timeZone: string): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      timeZoneName: 'short',
    }).formatToParts(new Date());
    return parts.find((part) => part.type === 'timeZoneName')?.value ?? timeZone;
  } catch {
    return timeZone;
  }
}
