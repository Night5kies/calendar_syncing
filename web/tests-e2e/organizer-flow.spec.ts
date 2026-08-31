import { expect, test } from '@playwright/test';

import {
  backendIsReachable,
  finalizeRequestViaApi,
  seedRequestViaApi,
} from './helpers';

test.describe('organizer + attendee flow', () => {
  test.beforeEach(async () => {
    const ok = await backendIsReachable();
    test.skip(!ok, 'Backend is not reachable at E2E_API_BASE_URL');
  });

  test('attendee can open the respond page and see proposals', async ({ page }) => {
    const seed = await seedRequestViaApi();
    await page.goto(`/events/${seed.requestId}/respond?token=${seed.inviteToken}`);
    await expect(page.getByText(/Responding as/i)).toBeVisible();
    await expect(page.getByText(/Pick what works/i)).toBeVisible();
    await expect(page.getByText(/Option 1/i)).toBeVisible();
  });

  test('attendee sees confirmed view + calendar deep-links after finalize', async ({ page }) => {
    const seed = await seedRequestViaApi();
    await finalizeRequestViaApi(seed.requestId, seed.proposalId);

    await page.goto(`/events/${seed.requestId}/respond?token=${seed.inviteToken}`);
    await expect(page.getByText(/This is confirmed/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /Add to Google Calendar/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Add to Outlook/i })).toBeVisible();
  });

  test('organizer detail page renders confirmed-event panel after finalize', async ({ page }) => {
    const seed = await seedRequestViaApi();
    await finalizeRequestViaApi(seed.requestId, seed.proposalId);

    await page.goto(`/request/${seed.requestId}`);
    await expect(page.getByText(/It.s booked/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /Open attendee view/i })).toBeVisible();
  });
});
