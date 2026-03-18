import type { Choice, RequestRecord, RequestTemplate } from './types';

const REQUESTS_KEY = 'syzy-web-requests';
const RESPONDER_KEY = 'syzy-web-responder-id';

function hasStorage() {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined';
}

function readRequests(): RequestRecord[] {
  if (!hasStorage()) {
    return [];
  }
  const raw = localStorage.getItem(REQUESTS_KEY);
  return raw ? (JSON.parse(raw) as RequestRecord[]) : [];
}

function writeRequests(requests: RequestRecord[]) {
  if (!hasStorage()) {
    return;
  }
  localStorage.setItem(REQUESTS_KEY, JSON.stringify(requests));
}

function durationToEnd(startIso: string, durationMinutes: number) {
  return new Date(new Date(startIso).getTime() + durationMinutes * 60000).toISOString();
}

function createId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function ensureSeedData() {
  if (!hasStorage()) {
    return;
  }
  const existing = readRequests();
  if (existing.length > 0) {
    return;
  }

  const now = new Date();
  const options = [
    new Date(now.getFullYear(), now.getMonth(), now.getDate() + 2, 18, 0, 0),
    new Date(now.getFullYear(), now.getMonth(), now.getDate() + 3, 19, 0, 0),
    new Date(now.getFullYear(), now.getMonth(), now.getDate() + 5, 17, 30, 0),
  ];

  const request: RequestRecord = {
    id: 'demo-dinner',
    title: 'Dinner with the crew',
    template: 'meal',
    durationMinutes: 90,
    timezone: 'America/New_York',
    notes: 'Trying to lock this in before the weekend slips away.',
    status: 'pending',
    participants: [
      { id: 'p1', label: 'Alex' },
      { id: 'p2', label: 'Jules' },
      { id: 'p3', label: 'Maya' },
      { id: 'p4', label: 'You' },
    ],
    options: options.map((start, index) => ({
      id: `demo-option-${index + 1}`,
      startIso: start.toISOString(),
      endIso: new Date(start.getTime() + 90 * 60000).toISOString(),
    })),
    selectedOptionId: null,
    responsesByDevice: {},
  };

  writeRequests([request]);
}

export function createRequest(input: {
  title: string;
  template: RequestTemplate;
  durationMinutes: number;
  timezone: string;
  notes: string;
  participants: string[];
  options: string[];
}) {
  const request: RequestRecord = {
    id: createId('request'),
    title: input.title,
    template: input.template,
    durationMinutes: input.durationMinutes,
    timezone: input.timezone,
    notes: input.notes,
    status: 'pending',
    participants: input.participants.map((participant) => ({
      id: createId('participant'),
      label: participant,
    })),
    options: input.options.map((startIso, index) => ({
      id: `option-${index + 1}`,
      startIso: new Date(startIso).toISOString(),
      endIso: durationToEnd(startIso, input.durationMinutes),
    })),
    selectedOptionId: null,
    responsesByDevice: {},
  };

  const requests = readRequests();
  writeRequests([request, ...requests]);
  return request;
}

export function getRequestById(id: string) {
  ensureSeedData();
  return readRequests().find((request) => request.id === id) ?? null;
}

export function getSharePath(id: string) {
  return `/respond/${id}`;
}

export function getResponderId() {
  if (!hasStorage()) {
    return 'server-responder';
  }
  const existing = localStorage.getItem(RESPONDER_KEY);
  if (existing) {
    return existing;
  }
  const next = createId('device');
  localStorage.setItem(RESPONDER_KEY, next);
  return next;
}

export function saveResponse(
  requestId: string,
  responderId: string,
  choices: Record<string, Choice>,
) {
  const requests = readRequests();
  const next = requests.map((request) => {
    if (request.id !== requestId) {
      return request;
    }

    return {
      ...request,
      responsesByDevice: {
        ...request.responsesByDevice,
        [responderId]: choices,
      },
    };
  });

  writeRequests(next);
}

export function setConfirmedOption(requestId: string, optionId: string) {
  const requests = readRequests();
  const next = requests.map((request) => {
    if (request.id !== requestId) {
      return request;
    }

    return {
      ...request,
      selectedOptionId: optionId,
      status: 'confirmed' as const,
    };
  });

  writeRequests(next);
}
