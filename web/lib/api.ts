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

export type ReminderPolicy = {
  initial_hours: number;
  followup_hours: number;
  max_per_participant: number;
};

export type ReminderPolicyInput = Partial<ReminderPolicy>;

export type OrganizerRequestDetail = {
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
  participants: Array<{
    id: string;
    display_name: string | null;
    email: string | null;
    phone: string | null;
    status: string;
    source: string;
    responded_at: string | null;
    invite_url: string | null;
  }>;
  progress: {
    responded_count: number;
    participant_count: number;
    outstanding_count: number;
    declined_count: number;
    unassigned_maybe_count: number;
  };
  outstanding_participants: Array<{
    id: string;
    display_name: string | null;
    email: string | null;
    phone: string | null;
  }>;
  tallies: Record<
    string,
    {
      picked: number;
      maybe: number;
      declined: number;
    }
  >;
  reminders: {
    enabled: boolean;
    response_deadline: string | null;
    last_reminded_at: string | null;
    sent_count: number;
    policy: ReminderPolicy;
    history: Array<{
      id: string;
      participant_id: string;
      channel: string;
      reason: string;
      sequence: number;
      status: string;
      target: string;
      created_at: string | null;
    }>;
  };
  share: {
    token: string;
    url: string;
    legacy_url?: string;
  } | null;
  confirmed_event: {
    id: string;
    proposal_id: string;
    provider: string | null;
    provider_event_id: string | null;
    artifact_uid: string | null;
    title: string;
    start_at: string | null;
    end_at: string | null;
    timezone: string;
    artifact_url: string | null;
  } | null;
};

export type ConfirmedEventPayload = {
  id: string;
  proposal_id: string;
  title: string;
  timezone: string;
  start_at: string | null;
  end_at: string | null;
  duration_min: number;
  location: string | null;
  video_link: string | null;
  notes: string | null;
  artifact_url: string | null;
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
  confirmed_event: ConfirmedEventPayload | null;
};

export type EventRespondContext = {
  event: {
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
  confirmed_event: ConfirmedEventPayload | null;
  invited_as?: {
    id: string;
    display_name: string | null;
    email: string | null;
    status: string;
    current_response: {
      proposal_id: string | null;
      choice: 'picked' | 'maybe' | 'declined' | null;
      comment: string | null;
    } | null;
  };
};

export type EventRespondResult =
  | {
      ok: true;
      status: 'saved';
      participant_id: string;
      choice: 'picked' | 'maybe' | 'declined';
      proposal_id: string | null;
      invite_url: string;
    }
  | {
      status: 'check_email';
      message: string;
      delivery_status: string;
    };

export async function createRequest(payload: {
  title: string;
  duration_min: number;
  timezone: string;
  event_type: string | null;
  location?: string | null;
  video_link?: string | null;
  notes: string | null;
  response_deadline: string | null;
  reminders_enabled: boolean;
  reminder_policy?: ReminderPolicyInput | null;
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

export async function pingNonResponders(requestId: string) {
  return request<{
    sent_count: number;
    skipped_count: number;
    outstanding_count: number;
    policy: ReminderPolicy;
    message_preview: string[];
  }>(`/v1/requests/${requestId}/reminders/ping`, {
    method: 'POST',
  });
}

export async function updateReminderSettings(
  requestId: string,
  payload: {
    reminders_enabled?: boolean;
    response_deadline?: string | null;
    reminder_policy?: ReminderPolicyInput | null;
  },
) {
  return request<{
    reminders_enabled: boolean;
    response_deadline: string | null;
    policy: ReminderPolicy;
  }>(`/v1/requests/${requestId}/reminders`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
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

export type AvailabilityWeekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';

export type AvailabilityWindow = { start: string; end: string };

export type AvailabilityWeeklyHours = Record<AvailabilityWeekday, AvailabilityWindow[]>;

export type AvailabilityRule = {
  id: string;
  timezone: string;
  weekly_hours: AvailabilityWeeklyHours;
  created_at: string | null;
  updated_at: string | null;
};

export type AvailabilityBlock = {
  id: string;
  start_at: string;
  end_at: string;
  type: 'busy' | 'private' | 'ooo';
  created_at: string | null;
};

export async function getAvailabilityRules() {
  return request<{ rules: AvailabilityRule[] }>(`/v1/availability/rules`);
}

export async function upsertAvailabilityRule(payload: {
  timezone: string;
  weekly_hours: AvailabilityWeeklyHours;
}) {
  return request<AvailabilityRule>(`/v1/availability/rules`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function getAvailabilityBlocks() {
  return request<{ blocks: AvailabilityBlock[] }>(`/v1/availability/blocks`);
}

export async function createAvailabilityBlock(payload: {
  start_at: string;
  end_at: string;
  type: AvailabilityBlock['type'];
}) {
  return request<AvailabilityBlock>(`/v1/availability/blocks`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export type SuggestSlotPayload = {
  start_at: string;
  end_at: string;
  score: number;
  reasons: string[];
};

export async function suggestProposals(
  requestId: string,
  payload: {
    start_date: string;
    end_date: string;
    days_of_week?: number[];
    time_windows?: Array<{ start_minute: number; end_minute: number }>;
    exclude_dates?: string[];
    limit?: number;
    replace_existing?: boolean;
    mode?: 'suggest' | 'preview';
  },
) {
  return request<{ suggestions: SuggestSlotPayload[] }>(`/v1/requests/${requestId}/suggest`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteAvailabilityBlock(blockId: string) {
  const response = await fetch(`${API_BASE}/v1/availability/blocks/${blockId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
}

export type CalendarConnectionPayload = {
  provider: string;
  provider_account_id: string;
  provider_email: string | null;
  connected_at: string | null;
  expires_at: string | null;
  scopes: Record<string, string> | null;
};

export async function getCalendarConnections() {
  return request<{ connections: CalendarConnectionPayload[] }>(`/v1/calendar/connections`);
}

export async function startGoogleConnect(returnTo: string) {
  const query = `?return_to=${encodeURIComponent(returnTo)}`;
  return request<{ authorize_url: string; state: string }>(
    `/v1/calendar/google/connect${query}`,
  );
}

export async function disconnectGoogle() {
  return request<{ ok: boolean; revoked: number }>(`/v1/calendar/google/disconnect`, {
    method: 'POST',
  });
}

export async function getEventResponseContext(eventId: string, inviteToken?: string | null) {
  const query = inviteToken ? `?token=${encodeURIComponent(inviteToken)}` : '';
  return request<EventRespondContext>(`/v1/events/${eventId}/respond${query}`);
}

export async function submitEventResponse(
  eventId: string,
  payload: {
    display_name?: string;
    email?: string;
    phone?: string;
    proposal_id: string | null;
    choice: 'picked' | 'maybe' | 'declined';
    comment?: string;
    invite_token?: string;
  },
) {
  return request<EventRespondResult>(`/v1/events/${eventId}/responses`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
