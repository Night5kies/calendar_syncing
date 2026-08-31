import { expect, test } from '@playwright/test';

test.describe('landing page', () => {
  test('renders the marketing copy and create CTA', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/SYZY/i);
    await expect(page.getByRole('link', { name: /create/i }).first()).toBeVisible();
  });
});
