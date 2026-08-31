export type RequestTemplate = 'meal' | 'coffee' | 'study' | 'hangout';
export type RequestStatus = 'pending' | 'confirmed';
export type Choice = 'yes' | 'maybe' | 'no';

export type Participant = {
  id: string;
  label: string;
};

export type RequestOption = {
  id: string;
  startIso: string;
  endIso: string;
};

export type RequestRecord = {
  id: string;
  title: string;
  template: RequestTemplate;
  durationMinutes: number;
  timezone: string;
  notes: string;
  status: RequestStatus;
  participants: Participant[];
  options: RequestOption[];
  selectedOptionId: string | null;
  responsesByDevice: Record<string, Record<string, Choice>>;
};

export type OptionTallies = Record<
  string,
  {
    yes: number;
    maybe: number;
    no: number;
  }
>;

export function getTallies(request: RequestRecord): OptionTallies {
  const tallies: OptionTallies = Object.fromEntries(
    request.options.map((option) => [
      option.id,
      { yes: 0, maybe: 0, no: 0 },
    ]),
  );

  Object.values(request.responsesByDevice).forEach((responseMap) => {
    Object.entries(responseMap).forEach(([optionId, choice]) => {
      tallies[optionId][choice] += 1;
    });
  });

  return tallies;
}

export function formatTallies(tally: { yes: number; maybe: number; no: number }) {
  return `${tally.yes} yes - ${tally.maybe} maybe - ${tally.no} no`;
}

export function formatRange(startIso: string, endIso: string, timezone: string) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: timezone,
  });

  return `${formatter.format(new Date(startIso))} - ${formatter.format(
    new Date(endIso),
  )}`;
}

export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function formatDateTime(iso: string | null, timezone: string) {
  if (!iso) {
    return 'Not set';
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: timezone,
  }).format(new Date(iso));
}
