import type { Metadata } from 'next';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

type EventMeta = {
  title: string;
  duration_min: number;
  timezone: string;
  event_type: string | null;
  location: string | null;
  status: string;
  proposals: Array<{
    start_at: string;
    end_at: string;
  }>;
};

async function fetchEventMeta(eventId: string): Promise<EventMeta | null> {
  try {
    const response = await fetch(`${API_BASE}/v1/events/${eventId}/respond`, {
      cache: 'no-store',
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as { event: EventMeta };
    return payload.event;
  } catch {
    return null;
  }
}

function formatPreviewRange(startIso: string, endIso: string, timezone: string) {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: timezone,
    });
    return `${formatter.format(new Date(startIso))} - ${formatter.format(new Date(endIso))}`;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const event = await fetchEventMeta(id);

  if (!event) {
    return {
      title: 'SYZY - respond',
      description: 'Pick a time. No account needed.',
    };
  }

  const isConfirmed = event.status === 'confirmed';
  const firstSlot = event.proposals[0];
  const previewSlot = firstSlot
    ? formatPreviewRange(firstSlot.start_at, firstSlot.end_at, event.timezone)
    : null;

  const descriptionParts: string[] = [];
  if (isConfirmed) {
    descriptionParts.push('Confirmed time inside.');
  } else if (previewSlot) {
    descriptionParts.push(`${event.proposals.length} options · first is ${previewSlot}`);
  } else {
    descriptionParts.push('Pick a time.');
  }
  if (event.location) {
    descriptionParts.push(event.location);
  }
  descriptionParts.push('No account needed.');

  const description = descriptionParts.join(' · ');
  const title = isConfirmed ? `${event.title} - confirmed` : `${event.title} - pick a time`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: 'website',
      siteName: 'SYZY',
    },
    twitter: {
      card: 'summary',
      title,
      description,
    },
  };
}

export default function EventRespondLayout({ children }: { children: React.ReactNode }) {
  return children;
}
