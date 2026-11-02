const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
function fixture(...args) { return JSON.parse(execFileSync(python, ['-m', 'tests.integration.ui_fixture', ...args], { cwd: root, encoding: 'utf8', windowsHide: true })); }
async function login(page, user) {
  await page.goto('/ui/');
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#loginButton').click();
  await expect(page.locator('#accountSection')).toBeVisible();
  await page.locator('#tuitionNav').click();
}
async function lookup(page, user) {
  await page.locator('#studentCode').fill(user.mssv);
  await page.locator('#lookupButton').click();
  await expect(page.locator('#invoiceSelection')).toBeVisible();
}
async function otpAndPay(page) {
  await page.locator('#sendOtpButton').click();
  await expect(page.locator('#otpForm')).toBeVisible();
  const key = (await page.locator('#paymentReference').innerText()).trim();
  const code = fixture('otp', key).otp;
  await page.locator('#otpCode').fill(code);
  await page.locator('#payButton').click();
  await expect(page.locator('#resultTitle')).toHaveText('Thành công');
  await expect(page.locator('#receiptMessage')).toContainText('Biên nhận đã được gửi', { timeout: 25000 });
  return key;
}
test('desktop: selected semester, all remaining, receipts and history', async ({ page }) => {
  const user = fixture();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await login(page, user); await lookup(page, user);
  await page.getByLabel('Chọn hóa đơn / học kỳ', { exact: true }).check();
  await page.getByRole('checkbox', { name: 'Chọn học kỳ IT-HK2', exact: true }).uncheck();
  await expect(page.locator('#selectedTotal')).toHaveText('2.000.000,00 ₫');
  await page.locator('#confirmSelectionButton').click();
  await expect(page.locator('#paymentTotal')).toHaveText('2.000.000,00 ₫');
  await otpAndPay(page);
  await expect(page.locator('#payerBalance')).toHaveText('8.000.000,00 ₫');
  await page.locator('#newPaymentButton').click(); await lookup(page, user);
  await expect(page.locator('#selectedTotal')).toHaveText('3.000.000,00 ₫');
  await page.locator('#confirmSelectionButton').click(); await otpAndPay(page);
  await expect(page.locator('#payerBalance')).toHaveText('5.000.000,00 ₫');
  await page.screenshot({ path: 'artifacts/payment-success-desktop.png', fullPage: true });
  await page.locator('#historyNav').click();
  await expect(page.locator('#historyRows tr')).toHaveCount(2);
  await expect(page.locator('#historyRows')).toContainText('Thành công');
  await page.screenshot({ path: 'artifacts/payment-history-desktop.png', fullPage: true });
  expect(errors).toEqual([]);
});
test('mobile: whole debt, usable layout and safe logout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const user = fixture(); await login(page, user); await lookup(page, user);
  await expect(page.locator('#selectedTotal')).toHaveText('5.000.000,00 ₫');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  await page.screenshot({ path: 'artifacts/payment-selection-mobile.png', fullPage: true });
  await page.locator('#confirmSelectionButton').click(); await otpAndPay(page);
  await page.screenshot({ path: 'artifacts/payment-success-mobile.png', fullPage: true });
  expect(await page.evaluate(() => Object.values(sessionStorage).some(value => value.includes('eyJ')))).toBeFalsy();
  await page.locator('#logoutButton').click();
  await expect(page.locator('#loginSection')).toBeVisible();
  await expect(page.locator('#payerFullName')).toHaveText('—');
  await expect(page.locator('#historyRows tr')).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem('ibanking.pendingPayment'))).toBeNull();
});
test('lost create and process replies keep the same payment ID', async ({ page }) => {
  const user = fixture(); await login(page, user); await lookup(page, user);
  const keys = []; let interceptedCreate = false;
  await page.route('**/api/v1/payments', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    keys.push(route.request().headers()['idempotency-key']);
    if (!interceptedCreate) { interceptedCreate = true; await route.fetch(); return route.abort('failed'); }
    return route.continue();
  });
  await page.locator('#confirmSelectionButton').click();
  await expect(page.locator('#pendingIntentCard')).toBeVisible();
  await page.locator('#retryIntentButton').click();
  await expect(page.locator('#paymentCard')).toBeVisible();
  expect(keys.length).toBe(2); expect(new Set(keys).size).toBe(1);
  await page.route('**/process', async route => { await route.fetch(); await route.abort('failed'); });
  await otpAndPay(page);
  await expect(page.locator('#payerBalance')).toHaveText('5.000.000,00 ₫');
  await page.locator('#historyNav').click();
  await expect(page.locator('#historyRows tr')).toHaveCount(1);
});
test('refresh resumes a pending UUID without storing a token or creating a new payment', async ({ page }) => {
  const user = fixture(); await login(page, user); await lookup(page, user);
  await page.locator('#confirmSelectionButton').click();
  await expect(page.locator('#paymentCard')).toBeVisible();
  const key = await page.locator('#paymentReference').innerText();
  await page.locator('#sendOtpButton').click();
  await expect(page.locator('#otpForm')).toBeVisible();
  await page.reload();
  await page.locator('#username').fill(user.username); await page.locator('#password').fill(user.password);
  await page.locator('#loginButton').click();
  await expect(page.locator('#paymentReference')).toHaveText(key);
  await expect(page.locator('#tuitionContent')).toBeVisible();
  await expect(page.locator('#otpForm')).toBeVisible();
  const code = fixture('otp', key.trim()).otp;
  await page.locator('#otpCode').fill(code); await page.locator('#payButton').click();
  await expect(page.locator('#resultTitle')).toHaveText('Thành công');
  await page.locator('#historyNav').click();
  await expect(page.locator('#historyRows tr')).toHaveCount(1);
});
