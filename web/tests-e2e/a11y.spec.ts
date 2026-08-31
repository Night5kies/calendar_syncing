import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { backendIsReachable, seedRequestViaApi } from './helpers';

type Impact = 'minor' | 'moderate' | 'serious' | 'critical';
const BLOCKING: Impact[] = ['serious', 'critical'];

async function auditBlocking(page: import('@playwright/test').Page, label: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => BLOCKING.includes(v.impact as Impact));
  if (blocking.length) {
    const summary = blocking
      .map((v) => `- [${v.impact}] ${v.id}: ${v.help}\n    ${v.nodes.map((n) => n.html).join('\n    ')}`)
      .join('\n');
    console.log(`\nA11y blocking violations on ${label}:\n${summary}\n`);
  }
  expect(blocking, `serious/critical a11y violations on ${label}`).toEqual([]);
}

test.describe('accessibility (axe)', () => {
  test('landing page', async ({ page }) => {
    await page.goto('/');
    await auditBlocking(page, 'landing');
  });

  test('create page', async ({ page }) => {
    await page.goto('/create');
    await page.waitForLoadState('networkidle');
    await auditBlocking(page, 'create');
  });

  test('signin page', async ({ page }) => {
    await page.goto('/signin');
    await auditBlocking(page, 'signin');
  });

  test('attendee respond page', async ({ page }) => {
    test.skip(!(await backendIsReachable()), 'Backend not reachable');
    const seed = await seedRequestViaApi();
    await page.goto(`/events/${seed.requestId}/respond?token=${seed.inviteToken}`);
    await page.waitForLoadState('networkidle');
    await auditBlocking(page, 'respond');
  });
});
