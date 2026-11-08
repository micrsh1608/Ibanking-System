const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
function fixture(...args){return JSON.parse(execFileSync(python,['-m','tests.integration.ui_fixture',...args],{cwd:root,encoding:'utf8',windowsHide:true}));}
async function login(page,username,password){
    await page.goto('/ui/');await page.locator('#username').fill(username);await page.locator('#password').fill(password);await page.locator('#loginButton').click();await expect(page.locator('#accountSection')).toBeVisible();
}
async function completeEmail(page) {
    await expect(page.locator('#emailVerificationPanel')).toBeVisible();
    const challenge=await page.evaluate(()=>currentUser.email_verification.challenge_id);
    const value=fixture('email-proof',challenge).code;
    await page.locator('#emailVerificationCode').fill(value);
    await page.locator('#confirmEmailButton').click();
    await expect(page.locator('#emailVerificationPanel')).toBeHidden();
    await expect(page.locator('#profileEmailStatus')).toHaveText('Email đang dùng đã được xác minh.');
}

test('existing account: no registration, login and persist profile without changing balance',async({page})=>{
    const user=fixture(), address=user.username.toLowerCase()+'-profile@example.test';
    await page.goto('/ui/');
    await expect(page.locator('#showRegisterButton')).toHaveCount(0);
    await expect(page.locator('#registerForm')).toHaveCount(0);
    expect((await page.request.post('/auth/register',{data:{username:'not_available',password:'Unused_123!'}})).status()).toBe(404);
    await page.screenshot({path:'artifacts/account-login-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
    await page.screenshot({path:'artifacts/account-login-mobile.png',fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await login(page,user.username,user.password);await expect(page.locator('#balance')).toHaveText('10.000.000,00 ₫');
    await page.locator('#profileNav').click();await page.locator('#editProfileButton').click();
    await page.locator('#profileEmail').fill(address);await page.locator('#profileFullName').fill('Nguyễn Minh Bình');await page.locator('#profilePassword').fill(user.password);
    await page.locator('#saveProfileButton').click();await completeEmail(page);await expect(page.locator('#email')).toHaveText(address);
    await expect(page.locator('#profilePassword')).toHaveValue('');
    await page.locator('#logoutButton').click();await login(page,user.username,user.password);
    await expect(page.locator('#balance')).toHaveText('10.000.000,00 ₫');
    await page.locator('#profileNav').click();await expect(page.locator('#fullName')).toHaveText('Nguyễn Minh Bình');
    await expect(page.locator('#email')).toHaveText(address);
    await page.locator('#editProfileButton').click();await page.screenshot({path:'artifacts/account-profile-desktop.png',fullPage:true});
});

test('mobile: update recipient, reject wrong password and send payment OTP/receipt to saved email',async({page})=>{
    await page.setViewportSize({width:390,height:844});const user=fixture();const address=user.username.toLowerCase()+'-updated@example.test';
    await login(page,user.username,user.password);await page.locator('#profileNav').click();await page.locator('#editProfileButton').click();
    await page.locator('#profileEmail').fill(address);await page.locator('#profilePassword').fill('WrongPassword_123!');await page.locator('#saveProfileButton').click();
    await expect(page.locator('#message')).toContainText('Mật khẩu xác nhận không đúng');
    await expect(page.locator('#profilePassword')).toHaveValue('');await page.locator('#profilePassword').fill(user.password);await page.locator('#saveProfileButton').click();await completeEmail(page);
    await expect(page.locator('#email')).toHaveText(address);
    await expect(page.locator('#profileMailNotice')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
    await page.screenshot({path:'artifacts/account-profile-mobile.png',fullPage:true});
    await page.locator('#tuitionNav').click();await expect(page.locator('#payerEmail')).toHaveText(address);
    await page.locator('#studentCode').fill(user.mssv);await expect(page.locator('#invoiceSelection')).toBeVisible();
    await page.locator('#acceptPaymentTerms').check();
    await page.locator('#confirmSelectionButton').click();await expect(page.locator('#otpForm')).toBeVisible();
    const key=(await page.locator('#paymentReference').innerText()).trim();expect(fixture('email-info',key).recipients).toEqual([address]);
    await page.locator('#otpCode').fill(fixture('otp',key).otp);await page.locator('#payButton').click();await expect(page.locator('#resultTitle')).toHaveText('Thành công');
    await expect(page.locator('#receiptMessage')).toContainText('Biên nhận đã được gửi',{timeout:25000});expect(fixture('email-info',key,'receipt').recipients).toEqual([address]);
    await page.screenshot({path:'artifacts/account-payment-email-mobile.png',fullPage:true});
});
