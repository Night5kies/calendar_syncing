import { request, type APIRequestContext } from '@playwright/test';

export const API_BASE_URL = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8000';

let cachedHealth: boolean | null = null;

export async function backendIsReachable(): Promise<boolean> {
  if (cachedHealth !== null) return cachedHealth;
  let api: APIRequestContext | null = null;
  try {
    api = await request.newContext({ baseURL: API_BASE_URL });
    const response = await api.get('/health', { timeout: 3000 });
    cachedHealth = response.ok();
  } catch {
    cachedHealth = false;
  } finally {
    await api?.dispose();
  }
  return cachedHealth;
}

export type CreatedRequest = {
  requestId: string;
  proposalId: string;
  participantId: string;
  shareToken: string;
  inviteToken: string;
};

export async function seedRequestViaApi(): Promise<CreatedRequest> {
  const api = await request.newContext({
    baseURL: API_BASE_URL,
    extraHTTPHeaders: { 'Content-Type': 'application/json' },
  });
  try {
    const created = await api.post('/v1/requests', {
      data: {
        title: `e2e Smoke ${Date.now()}`,
        duration_min: 30,
        timezone: 'America/New_York',
        event_type: 'coffee',
        notes: 'Playwright smoke test',
        reminders_enabled: false,
      },
    });
    if (!created.ok()) throw new Error(`create request failed: ${created.status()} ${await created.text()}`);
    const { id: requestId } = (await created.json()) as { id: string };

    const proposal = await api.post(`/v1/requests/${requestId}/proposals`, {
      data: {
        rank: 1,
        start_at: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
      },
    });
    if (!proposal.ok()) throw new Error(`add proposal failed: ${proposal.status()} ${await proposal.text()}`);
    const { id: proposalId } = (await proposal.json()) as { id: string };

    const participant = await api.post(`/v1/requests/${requestId}/participants`, {
      data: {
        display_name: 'Playwright Guest',
        email: `pw-${Date.now()}@example.com`,
      },
    });
    if (!participant.ok())
      throw new Error(`add participant failed: ${participant.status()} ${await participant.text()}`);
    const participantPayload = (await participant.json()) as { id: string; invite_url: string };

    const inviteToken = new URL(participantPayload.invite_url).searchParams.get('token') ?? '';

    const share = await api.post(`/v1/share/${requestId}`);
    if (!share.ok()) throw new Error(`create share failed: ${share.status()} ${await share.text()}`);
    const { token: shareToken } = (await share.json()) as { token: string };

    return {
      requestId,
      proposalId,
      participantId: participantPayload.id,
      shareToken,
      inviteToken,
    };
  } finally {
    await api.dispose();
  }
}

export async function finalizeRequestViaApi(requestId: string, proposalId: string): Promise<void> {
  const api = await request.newContext({
    baseURL: API_BASE_URL,
    extraHTTPHeaders: { 'Content-Type': 'application/json' },
  });
  try {
    const response = await api.post(`/v1/requests/${requestId}/finalize`, {
      data: { proposal_id: proposalId },
    });
    if (!response.ok()) {
      throw new Error(`finalize failed: ${response.status()} ${await response.text()}`);
    }
  } finally {
    await api.dispose();
  }
}
