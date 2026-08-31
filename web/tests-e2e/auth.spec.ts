import { expect, test } from '@playwright/test';

// The e2e dev server runs without Supabase env, so auth is disabled and the
// app falls back to backend dev-auth. These specs lock that dev-mode behavior:
// /signin explains auth is off, and the organizer pages stay reachable.
test.describe('auth (dev mode, no Supabase env)', () => {
  test('signin page reports auth is not configured', async ({ page }) => {
    await page.goto('/signin');
    await expect(page.getByText(/Auth is not configured/i)).toBeVisible();
  });

  test('create page is reachable without sign-in', async ({ page }) => {
    await page.goto('/create');
    // Not redirected to /signin and the create flow renders.
    await expect(page).toHaveURL(/\/create$/);
  });
});
