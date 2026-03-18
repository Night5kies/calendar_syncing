const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export type OrganizerRequestDetail = {
  id: string;
  title: string;
  duration_min: number;
  timezone: string;
  event_type: string | null;
  notes: string | null;
  status: string;
  proposals: Array<{
    id: string;
    rank: number;
    start_at: string;
    end_at: string;
    score: number | null;
  }>;
  participants: Array<{
    id: string;
    display_name: string | null;
    email: string | null;
    phone: string | null;
    status: string;
    responded_at: string | null;
  }>;
  progress: {
    responded_count: number;
    participant_count: number;
    outstanding_count: number;
    declined_count: number;
    unassigned_maybe_count: number;
  };
  tallies: Record<
    string,
    {
      picked: number;
      maybe: number;
      declined: number;
    }
  >;
  share: {
    token: string;
    url: string;
  } | null;
};

export type PublicSharePayload = {
  request: {
    id: string;
    title: string;
    duration_min: number;
    timezone: string;
    event_type: string | null;
    location: string | null;
    video_link: string | null;
    notes: string | null;
    status: string;
    proposals: Array<{
      id: string;
      rank: number;
      start_at: string;
      end_at: string;
      score: number | null;
    }>;
  };
};

export async function createRequest(payload: {
  title: string;
  duration_min: number;
  timezone: string;
  event_type: string | null;
  notes: string | null;
}) {
  return request<{ id: string }>('/v1/requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function addParticipant(
  requestId: string,
  payload: { display_name: string; email?: string; phone?: string },
) {
  return request<{ id: string }>(`/v1/requests/${requestId}/participants`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function addProposal(
  requestId: string,
  payload: { rank: number; start_at: string },
) {
  return request<{ id: string }>(`/v1/requests/${requestId}/proposals`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function createShareLink(requestId: string) {
  return request<{ token: string; url: string }>(`/v1/share/${requestId}`, {
    method: 'POST',
  });
}

export async function getOrganizerRequest(requestId: string) {
  return request<OrganizerRequestDetail>(`/v1/requests/${requestId}`);
}

export async function finalizeRequest(requestId: string, proposalId: string) {
  return request<{ id: string }>(`/v1/requests/${requestId}/finalize`, {
    method: 'POST',
    body: JSON.stringify({ proposal_id: proposalId }),
  });
}

export async function getPublicShare(token: string) {
  return request<PublicSharePayload>(`/v1/share/public/${token}`);
}

export async function submitPublicResponse(
  token: string,
  payload: {
    display_name: string;
    guest_key: string;
    proposal_id: string | null;
    choice: 'picked' | 'maybe' | 'declined';
    comment?: string;
    email?: string;
    phone?: string;
  },
) {
  return request<{ ok: boolean }>(`/v1/share/public/${token}/responses`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
