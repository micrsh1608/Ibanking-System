const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
function fixture(...args) { return JSON.parse(execFileSync(python, ['-m', 'tests.integration.ui_fixture', ...args], { cwd: root, encoding: 'utf8', windowsHide: true })); }
async function submit(page, user) {
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#loginButton').click();
}
async function login(page, user) {
  await page.goto('/ui/'); await submit(page, user);
  await expect(page.locator('#accountSection')).toBeVisible();
}
function denied(status, detail) { return { status, contentType: 'application/json', body: JSON.stringify({ detail }) }; }

test('login: generic credential errors, normalized username and all required user information', async ({ page }) => {
  const user = fixture(); await page.goto('/ui/');
  await submit(page, { ...user, password: 'WrongPassword_123!' });
  await expect(page.locator('#message')).toHaveText('Sai tên đăng nhập hoặc mật khẩu');
  await expect(page.locator('#accountSection')).toBeHidden();
  await expect(page.locator('#password')).toHaveValue('');
  await submit(page, { username: 'no_such_' + randomUUID().slice(0, 8), password: user.password });
  await expect(page.locator('#message')).toHaveText('Sai tên đăng nhập hoặc mật khẩu');
  await page.screenshot({ path: 'artifacts/account-login-invalid.png', fullPage: true });
  await submit(page, { ...user, username: '  ' + user.username.toUpperCase() + '  ' });
  await expect(page.locator('#accountSection')).toBeVisible();
  await expect(page.locator('#balance')).toHaveText('10.000.000,00 ₫');
  await page.locator('#balanceToggle').click(); await expect(page.locator('#balance')).toHaveText('••••••••');
  await page.locator('#balanceToggle').click(); await expect(page.locator('#balance')).toHaveText('10.000.000,00 ₫');
  await page.locator('#profileNav').click();
  await expect(page.locator('#fullName')).toHaveText('Nguyễn Minh An');
  await expect(page.locator('#userName')).toHaveText(user.username);
  await expect(page.locator('#phone')).toHaveText('0900000099');
  await expect(page.locator('#email')).toContainText('@example.test');
  await page.screenshot({ path: 'artifacts/account-login-profile.png', fullPage: true });
  await page.locator('#tuitionNav').click(); await expect(page.locator('#tuitionContent')).toBeVisible();
  await expect(page.locator('#payerFullName')).toHaveText('Nguyễn Minh An');
  await page.locator('#historyNav').click(); await expect(page.locator('#historyEmpty')).toBeVisible();
  expect(await page.evaluate(() => [...Object.values(localStorage), ...Object.values(sessionStorage)].some(v => v.includes('eyJ')))).toBeFalsy();
});

test('disabled user cannot log in or see the account dashboard', async ({ page }) => {
  const user = fixture('scenario', 'inactive'); await page.goto('/ui/'); await submit(page, user);
  await expect(page.locator('#message')).toHaveText('Người dùng đã bị vô hiệu hóa');
  await expect(page.locator('#accountSection')).toBeHidden(); await expect(page.locator('#loginSection')).toBeVisible();
  await expect(page.locator('#password')).toHaveValue('');
});

test('expired profile save clears session and personal information', async ({ page }) => {
  const user = fixture(); await login(page, user); await page.locator('#profileNav').click();
  await page.locator('#editProfileButton').click(); await page.locator('#profilePassword').fill(user.password);
  await page.route('**/users/me', route => route.request().method() === 'PUT'
    ? route.fulfill(denied(401, 'Token không hợp lệ hoặc đã hết hạn')) : route.continue());
  await page.locator('#saveProfileButton').click();
  await expect(page.locator('#loginSection')).toBeVisible(); await expect(page.locator('#accountSection')).toBeHidden();
  await expect(page.locator('#message')).toContainText('Phiên đăng nhập đã hết hạn');
  for (const id of ['fullName', 'email', 'phone', 'accountNumber']) await expect(page.locator('#' + id)).toHaveText('');
  await expect(page.locator('#profilePassword')).toHaveValue('');
  await expect(page.locator('#historyRows tr')).toHaveCount(0);
  expect(await page.evaluate(() => accessToken)).toBeNull();
});

test('disabled session on profile save is distinguished from a wrong confirmation password', async ({ page }) => {
  const user = fixture(); await login(page, user); await page.locator('#profileNav').click();
  await page.locator('#editProfileButton').click(); await page.locator('#profilePassword').fill(user.password);
  await page.route('**/users/me', route => route.fulfill(denied(403, 'Người dùng đã bị vô hiệu hóa')));
  await page.locator('#saveProfileButton').click();
  await expect(page.locator('#loginSection')).toBeVisible(); await expect(page.locator('#accountSection')).toBeHidden();
  await expect(page.locator('#message')).toContainText('Người dùng đã bị vô hiệu hóa');
  expect(await page.evaluate(() => accessToken)).toBeNull();
});

test('logout, account switching and a late profile response cannot expose the previous user or history', async ({ page }) => {
  const first = fixture(), second = fixture(); await login(page, first); await page.locator('#profileNav').click();
  const firstEmail = await page.locator('#email').innerText(), firstAccount = await page.locator('#accountNumber').innerText();
  const key = randomUUID();
  const created = await page.evaluate(async ({ key, mssv }) => {
    const response = await fetch('/api/v1/payments', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + accessToken, 'Idempotency-Key': key }, body: JSON.stringify({ mssv, selection_mode: 'ALL_UNPAID', terms_accepted: true }) });
    return response.status;
  }, { key, mssv: first.mssv });
  expect(created).toBe(201);
  await page.locator('#historyNav').click(); await expect(page.locator('#historyRows tr')).toHaveCount(1);
  await expect(page.locator('#historyRows')).toContainText(key.replaceAll('-', '').toUpperCase());
  let release, fetched; const gate = new Promise(resolve => { release = resolve; }), ready = new Promise(resolve => { fetched = resolve; });
  let delayed = false;
  await page.route('**/users/me', async route => {
    if (delayed) return route.continue(); delayed = true;
    const response = await route.fetch(); fetched(); await gate; await route.fulfill({ response });
  });
  try {
    await page.locator('#refreshButton').click(); await ready;
    await page.locator('#logoutButton').click();
    await expect(page.locator('#email')).toHaveText(''); await expect(page.locator('#historyRows tr')).toHaveCount(0);
    await submit(page, second); await expect(page.locator('#accountSection')).toBeVisible(); await page.locator('#profileNav').click();
    const secondEmail = await page.locator('#email').innerText(); expect(secondEmail).not.toBe(firstEmail);
    expect(await page.locator('#accountNumber').innerText()).not.toBe(firstAccount);
    const completed = page.waitForResponse(response => response.url().endsWith('/users/me') && response.status() === 200);
    release(); await completed; await expect(page.locator('#refreshButton')).toBeEnabled();
    await expect(page.locator('#email')).toHaveText(secondEmail);
    await page.locator('#historyNav').click(); await expect(page.locator('#historyEmpty')).toBeVisible();
    await expect(page.locator('#historyRows tr')).toHaveCount(0);
  } finally { release(); }
});

test('incomplete account loading leaves login visible and clears the temporary token', async ({ page }) => {
  const user = fixture(); await page.goto('/ui/');
  await page.route('**/accounts/me', route => route.fulfill(denied(503, 'Chưa lấy được thông tin tài khoản')));
  await submit(page, user);
  await expect(page.locator('#message')).toContainText('Chưa lấy được thông tin tài khoản');
  await expect(page.locator('#loginSection')).toBeVisible(); await expect(page.locator('#accountSection')).toBeHidden();
  await expect(page.locator('#password')).toHaveValue(''); expect(await page.evaluate(() => accessToken)).toBeNull();
});
