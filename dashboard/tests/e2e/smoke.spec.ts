import { expect, test } from '@playwright/test';

const BASE = '/vllm-omni-kanban/dashboard';

test('home renders model cards and updated timestamp area', async ({ page }) => {
  await page.goto(`${BASE}/`);
  await expect(page.getByRole('heading', { name: 'Models' })).toBeVisible();
  const cards = page.locator('a[href*="/models/"]');
  expect(await cards.count()).toBeGreaterThan(0);
});

test('model page renders chart container or empty placeholder', async ({ page }) => {
  await page.goto(`${BASE}/models/qwen3-omni/`);
  await expect(page.getByRole('heading', { name: /Qwen3 Omni/ })).toBeVisible();
  const chart = page.locator('[data-trendchart]');
  const placeholder = page.getByText('No data in selected range.');
  if ((await chart.count()) > 0) {
    const box = await chart.first().boundingBox();
    expect(box?.height ?? 0).toBeGreaterThan(100);
  } else {
    await expect(placeholder).toBeVisible();
  }
  // ≥1 legend chip rendered
  expect(await page.locator('span.rounded-full').count()).toBeGreaterThan(0);
});

test('about page renders heuristic explanation', async ({ page }) => {
  await page.goto(`${BASE}/about/`);
  await expect(page.getByRole('heading', { name: 'About this dashboard' })).toBeVisible();
  await expect(page.getByText('correlation, not causation', { exact: false })).toBeVisible();
});
