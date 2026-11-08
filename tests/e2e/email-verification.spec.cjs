const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
function fixture(...args) { return JSON.parse(execFileSync(python, ['-m', 'tests.integration.ui_fixture', ...args], { cwd: root, encoding: 'utf8', windowsHide: true })); }
async function login(page, user) {
  await page.goto('/ui/'); await page.locator('#username').fill(user.username); await page.locator('#password').fill(user.password); await page.locator('#loginButton').click();
  await expect(page.locator('#accountSection')).toBeVisible();
}
async function requestProof(page, user, target) {
  await page.locator('#profileNav').click(); await page.locator('#editProfileButton').click();
  await page.locator('#profileEmail').fill(target); await page.locator('#profilePassword').fill(user.password); await page.locator('#saveProfileButton').click();
  await expect(page.locator('#emailVerificationPanel')).toBeVisible();
}

test('SMTP acceptance of a candidate without inbox proof never activates it or enables payment', async ({ page }) => {
  const user=fixture('scenario','email-unverified'),target='unconfirmed-'+randomUUID().slice(0,8)+'@example.test';
  await login(page,user);await page.locator('#profileNav').click();const original=await page.locator('#email').innerText();
  await requestProof(page,user,target);
  await expect(page.locator('#pendingEmailAddress')).toHaveText(target);await expect(page.locator('#email')).toHaveText(original);
  await expect(page.locator('#profileEmailStatus')).toContainText('chưa được xác minh');
  await expect(page.locator('#resendEmailButton')).toBeDisabled();
  await page.screenshot({path:'artifacts/email-proof-pending.png',fullPage:true});
  await page.locator('#tuitionNav').click();await page.locator('#studentCode').fill(user.mssv);await expect(page.locator('#invoiceSelection')).toBeVisible();
  await page.locator('#acceptPaymentTerms').check();await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
  await expect(page.locator('#payerDetailsWarning')).toContainText('Email chưa được xác minh');
  await expect(page.locator('#payerEmail')).toHaveText(original);
  const response=await page.evaluate(async mssv=>{
    const result=await fetch('/api/v1/payments',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+accessToken,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({mssv,terms_accepted:true})});return result.status;
  },user.mssv);
  expect(response).toBe(409);
  await page.locator('#profileNav').click();await page.locator('#cancelEmailButton').click();
  await expect(page.locator('#emailVerificationPanel')).toBeHidden();await expect(page.locator('#email')).toHaveText(original);
});

test('wrong email code keeps the old address; pending proof survives reload and correct code activates it', async ({ page }) => {
  const user=fixture('scenario','email-unverified'),target='confirmed-'+randomUUID().slice(0,8)+'@example.test';
  await page.setViewportSize({width:390,height:844});await login(page,user);await requestProof(page,user,target);
  const challenge=await page.evaluate(()=>currentUser.email_verification.challenge_id),value=fixture('email-proof',challenge).code;
  const original=await page.locator('#email').innerText();
  await page.locator('#emailVerificationCode').fill(value==='000000'?'111111':'000000');await page.locator('#confirmEmailButton').click();
  await expect(page.locator('#message')).toContainText('Mã xác minh email không đúng');await expect(page.locator('#email')).toHaveText(original);
  await page.screenshot({path:'artifacts/email-proof-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await login(page,user);await page.locator('#profileNav').click();await expect(page.locator('#emailVerificationPanel')).toBeVisible();
  await expect(page.locator('#pendingEmailAddress')).toHaveText(target);
  await page.locator('#emailVerificationCode').fill(value);await page.locator('#confirmEmailButton').click();
  await expect(page.locator('#email')).toHaveText(target);await expect(page.locator('#emailVerificationPanel')).toBeHidden();
  await expect(page.locator('#profileEmailStatus')).toHaveText('Email đang dùng đã được xác minh.');
  await page.screenshot({path:'artifacts/email-proof-confirmed.png',fullPage:true});
});

test('SMTP failure cannot show a saved or verified replacement email', async ({ page }) => {
  const user=fixture();await login(page,user);await page.locator('#profileNav').click();const original=await page.locator('#email').innerText();
  await page.route('**/users/me',route=>route.request().method()==='PUT'?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Chưa gửi được mã xác minh email. Hồ sơ và email đang dùng chưa thay đổi.'})}):route.continue());
  await page.locator('#editProfileButton').click();await page.locator('#profileEmail').fill('not-saved@example.test');await page.locator('#profilePassword').fill(user.password);await page.locator('#saveProfileButton').click();
  await expect(page.locator('#message')).toContainText('Chưa gửi được mã xác minh email');
  await expect(page.locator('#email')).toHaveText(original);await expect(page.locator('#emailVerificationPanel')).toBeHidden();
  await expect(page.locator('#profilePassword')).toHaveValue('');
});

test('successful save shows and focuses the code entry without relying on another profile fetch', async ({ page }) => {
  const user=fixture('scenario','email-unverified'),target='direct-'+randomUUID().slice(0,8)+'@example.test';
  await login(page,user);await page.locator('#profileNav').click();
  const original=await page.locator('#email').innerText();
  await page.route('**/users/me',route=>route.request().method()==='GET'?route.fulfill({status:503,contentType:'application/json',body:'{"detail":"Temporary read failure"}'}):route.continue());
  await requestProof(page,user,target);
  await expect(page.locator('#emailVerificationCode')).toBeFocused();
  await expect(page.locator('#emailVerificationCode')).toBeInViewport();
  await expect(page.locator('#email')).toHaveText(original);
  const challenge=await page.evaluate(()=>currentUser.email_verification.challenge_id);
  await page.locator('#emailVerificationCode').fill(fixture('email-proof',challenge).code);await page.locator('#confirmEmailButton').click();
  await expect(page.locator('#email')).toHaveText(target);await expect(page.locator('#emailVerificationPanel')).toBeHidden();
});

test('a lost save response recovers the mailed challenge and exposes its code input', async ({ page }) => {
  const user=fixture('scenario','email-unverified'),target='recover-'+randomUUID().slice(0,8)+'@example.test';
  await login(page,user);await page.locator('#profileNav').click();const original=await page.locator('#email').innerText();
  await page.route('**/users/me',async route=>{
    if(route.request().method()!=='PUT')return route.continue();
    await route.fetch();await route.abort('failed');
  });
  await requestProof(page,user,target);
  await expect(page.locator('#emailVerificationCode')).toBeFocused();
  await expect(page.locator('#pendingEmailAddress')).toHaveText(target);await expect(page.locator('#email')).toHaveText(original);
  await expect(page.locator('#message')).toContainText('Đã khôi phục yêu cầu chờ');
  await page.screenshot({path:'artifacts/email-proof-recovered.png',fullPage:true});
  const challenge=await page.evaluate(()=>currentUser.email_verification.challenge_id);
  await page.locator('#emailVerificationCode').fill(fixture('email-proof',challenge).code);await page.locator('#confirmEmailButton').click();
  await expect(page.locator('#email')).toHaveText(target);
});
