const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

// These tests never prepare users or send messages against the main demo stack.
test.skip(process.env.IBANKING_TEST_PROFILE !== 'isolated', 'Requires the isolated SQL/Mailpit acceptance stack');

function fixture(action, value) {
  return JSON.parse(execFileSync(python, ['-m', 'tests.integration.web_consistency_fixture', action, ...(value ? [value] : [])],
    { cwd: root, encoding: 'utf8', windowsHide: true, timeout: 60000 }));
}
function audit(state, keys) {
  const input = Buffer.from(JSON.stringify({ ...state, payment_ids: keys })).toString('base64');
  return fixture('audit', input);
}
async function login(page, user) {
  await page.goto('/ui/');
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#loginButton').click();
  await expect(page.locator('#accountSection')).toBeVisible();
  await page.locator('#tuitionNav').click();
}
async function draft(page, actor) {
  await page.locator('#studentCode').fill(actor.mssv);
  await expect(page.locator('#invoiceSelection')).toBeVisible();
  await page.locator('#acceptPaymentTerms').check();
  await page.locator('#confirmSelectionButton').click();
  await expect(page.locator('#otpForm')).toBeVisible();
  const key = (await page.locator('#paymentReference').innerText()).trim();
  const code = fixture('otp', key).otp;
  await page.locator('#otpCode').fill(code);
  await expect(page.locator('#payButton')).toBeEnabled();
  return key;
}
async function twoSessions(browser, baseURL, state) {
  const contexts = await Promise.all([browser.newContext({ baseURL }), browser.newContext({ baseURL })]);
  const pages = await Promise.all(contexts.map(context => context.newPage()));
  try {
    await Promise.all(pages.map((page, index) => login(page, state.actors[index])));
    // Browser requests create both independent snapshots before either processes.
    const keys = await Promise.all(pages.map((page, index) => draft(page, state.actors[index])));
    expect(new Set(keys).size).toBe(2);
    return { contexts, pages, keys };
  } catch (error) {
    await Promise.all(contexts.map(context => context.close()));
    throw error;
  }
}

for (const scenario of ['balance', 'tuition']) {
  test(`two real Web sessions preserve ${scenario === 'balance' ? 'one-account funds' : 'one whole tuition group'}`, async ({ browser, baseURL }) => {
    const state = fixture('prepare', scenario);
    const sessions = await twoSessions(browser, baseURL, state);
    const { pages, keys } = sessions;
    const processRequests = [0, 0];
    pages.forEach((page, index) => page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith(`/${keys[index]}/process`)) processRequests[index]++;
    }));
    try {
      // No HTTP interception, delayed responses, JS barriers or backend payment helpers.
      const clicks = await Promise.allSettled(pages.map(page => page.locator('#payButton').click({ timeout: 7000 })));
      await expect.poll(async () => (await Promise.all(pages.map(page => page.locator('#resultTitle').textContent())))
        .filter(value => value === 'Thành công').length, { timeout: 30000 }).toBe(1);
      for (let index = 0; index < pages.length; index++) {
        await expect.poll(async () => processRequests[index] > 0 ||
          (await pages[index].locator('#paymentEligibilityNotice').isVisible() &&
           await pages[index].locator('#cancelDraftButton').isVisible() &&
           await pages[index].locator('#cancelDraftButton').isEnabled()), { timeout: 20000 }).toBe(true);
        if (processRequests[index] === 0) {
          // A live update may correctly disable the losing draft before its click.
          await expect(pages[index].locator('#payButton')).toBeDisabled();
          await expect(pages[index].locator('#cancelDraftButton')).toBeVisible();
          await pages[index].locator('#cancelDraftButton').click();
          await expect(pages[index].locator('#lookupCard')).toBeVisible();
        } else {
          expect(clicks[index].status).toBe('fulfilled');
          await expect(pages[index].locator('#resultTitle')).toHaveText(/^(Thành công|Không thành công)$/);
        }
      }
      expect(processRequests.reduce((sum, count) => sum + count, 0)).toBeGreaterThanOrEqual(1);
      const result = audit(state, keys);
      expect(result.checks).toMatchObject({ exactly_two_browser_payments: true, one_success_one_failure: true,
        only_one_debit_no_refund: true, exact_balances: true, snapshot_totals: true, whole_invoice_groups: true,
        one_receipt_with_frozen_route: true, reservations_converged: true });
      expect(result.consistent).toBe(true);
      if (scenario === 'balance') expect(result.accounts.map(row => row.balance)).toEqual(['3000000.00']);
      else expect(result.accounts.map(row => row.balance).sort()).toEqual(['10000000.00', '5000000.00']);
    } finally {
      await Promise.all(sessions.contexts.map(context => context.close()));
    }
  });
}

test('another Web session refreshes the real balance and can cancel its blocked draft without spending', async ({ browser, baseURL }) => {
  const state = fixture('prepare', 'balance');
  const sessions = await twoSessions(browser, baseURL, state);
  const { pages, keys } = sessions;
  let secondSessionProcesses = 0;
  pages[1].on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith(`/${keys[1]}/process`)) secondSessionProcesses++;
  });
  try {
    await pages[0].locator('#payButton').click();
    await expect(pages[0].locator('#resultTitle')).toHaveText('Thành công');
    // Returning to the second browser triggers the same focus/visibility behavior as a user.
    await pages[1].bringToFront();
    await expect(pages[1].locator('#payerBalance')).toHaveText('3.000.000,00 ₫', { timeout: 15000 });
    await expect(pages[1].locator('#payButton')).toBeDisabled();
    await expect(pages[1].locator('#cancelDraftButton')).toBeEnabled();
    await pages[1].locator('#cancelDraftButton').click();
    await expect(pages[1].locator('#lookupCard')).toBeVisible();
    expect(secondSessionProcesses).toBe(0);
    await pages[1].locator('#historyNav').click();
    await expect(pages[1].locator(`#historyRows tr[data-payment-id="${keys[1]}"]`)).toHaveAttribute('data-payment-status', 'FAILED');
    const result = audit(state, keys);
    expect(result.consistent).toBe(true);
    expect(result.accounts.map(row => row.balance)).toEqual(['3000000.00']);
    expect(result.entries).toHaveLength(1);
    expect(result.entries[0].payment_id).toBe(keys[0]);
    expect(result.reservations).toEqual([{ payment_id: keys[0], status: 'PAID' }]);
  } finally {
    await Promise.all(sessions.contexts.map(context => context.close()));
  }
});
