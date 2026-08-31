/**
 * The backend has no "list my requests" endpoint yet, so an organizer who
 * closes the tab loses the way back to a request they just sent. This keeps a
 * short local trail in the browser so the flow is round-trippable. It is a
 * convenience, never a source of truth — the request page always refetches.
 */

const KEY = 'syzy:recent-requests';
const LIMIT = 8;

export type RecentRequest = {
  id: string;
  title: string;
  createdAt: string;
  status?: string;
};

function read(): RecentRequest[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is RecentRequest =>
        typeof entry === 'object' && entry !== null && typeof (entry as RecentRequest).id === 'string',
    );
  } catch {
    return [];
  }
}

function write(entries: RecentRequest[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(entries.slice(0, LIMIT)));
  } catch {
    // storage disabled or full — the trail is optional
  }
}

export function listRecentRequests(): RecentRequest[] {
  return read();
}

export function rememberRequest(entry: RecentRequest) {
  const rest = read().filter((existing) => existing.id !== entry.id);
  write([entry, ...rest]);
}

export function forgetRequest(id: string) {
  write(read().filter((entry) => entry.id !== id));
}
