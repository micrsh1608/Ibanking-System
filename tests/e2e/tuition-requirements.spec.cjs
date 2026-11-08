const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
function fixture(...args){return JSON.parse(execFileSync(python,['-m','tests.integration.ui_fixture',...args],{cwd:root,encoding:'utf8',windowsHide:true}));}
async function login(page,user){
    await page.goto('/ui/');await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#loginButton').click();await expect(page.locator('#accountSection')).toBeVisible();await page.locator('#tuitionNav').click();
}
for(const scenario of ['zero-balance','missing-phone','locked','no-invoices']){
    test(`confirmation stays disabled for ${scenario}`,async({page})=>{
        const user=fixture('scenario',scenario);await login(page,user);
        let created=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/v1/payments'))created++;});
        await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
        await page.locator('#studentCode').fill(user.mssv);await expect(page.locator('#invoiceSelection')).toBeVisible();
        if(scenario!=='no-invoices')await page.locator('#acceptPaymentTerms').check();
        await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
        await expect(page.locator('#eligibilityNotice')).toBeVisible();
        if(scenario==='zero-balance'){
            await expect(page.locator('#balanceWarning')).toBeVisible();
            await page.screenshot({path:'artifacts/tuition-insufficient-balance.png',fullPage:true});
        }
        if(scenario==='missing-phone')await expect(page.locator('#payerProfileButton')).toBeVisible();
        expect(created).toBe(0);
    });
}
test('balance exactly equal to whole debt is sufficient; consent is required',async({page})=>{
    const user=fixture('scenario','exact-balance');await login(page,user);
    await page.locator('#studentCode').fill(user.mssv);await expect(page.locator('#invoiceSelection')).toBeVisible();
    await expect(page.locator('#availableBalance')).toHaveText('5.000.000,00 ₫');
    await expect(page.locator('#selectedTotal')).toHaveText('5.000.000,00 ₫');
    await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
    await page.locator('#acceptPaymentTerms').check();await expect(page.locator('#confirmSelectionButton')).toBeEnabled();
    await page.locator('#acceptPaymentTerms').uncheck();await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
});
test('editing MSSV clears the old student/amount immediately and a missing MSSV cannot pay',async({page})=>{
    const user=fixture();await login(page,user);
    await page.locator('#studentCode').fill(user.mssv);await expect(page.locator('#invoiceSelection')).toBeVisible();
    await page.locator('#acceptPaymentTerms').check();await expect(page.locator('#confirmSelectionButton')).toBeEnabled();
    await page.locator('#studentCode').fill('NO_SUCH_STUDENT');
    await expect(page.locator('#invoiceSelection')).toBeHidden();await expect(page.locator('#studentName')).toHaveText('');
    await expect(page.locator('#selectedTotal')).toHaveText('0,00 ₫');
    await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
    await expect(page.locator('#tuitionNotice')).toContainText('Không tìm thấy MSSV');
});
test('a late lookup response cannot replace the most recently entered MSSV',async({page})=>{
    const first=fixture(),second=fixture();await login(page,first);
    await page.route('**/api/v1/tuition/'+first.mssv,async route=>{
        const response=await route.fetch();await new Promise(r=>setTimeout(r,1800));await route.fulfill({response});
    });
    const requested=page.waitForRequest(r=>r.url().endsWith('/api/v1/tuition/'+first.mssv));
    const lateResponse=page.waitForResponse(r=>r.url().endsWith('/api/v1/tuition/'+first.mssv));
    await page.locator('#studentCode').fill(first.mssv);await requested;
    await page.locator('#studentCode').fill(second.mssv);
    await expect(page.locator('#studentMssv')).toHaveText('MSSV: '+second.mssv);
    await lateResponse;
    await expect(page.locator('#studentMssv')).toHaveText('MSSV: '+second.mssv);
    await expect(page.locator('#acceptPaymentTerms')).not.toBeChecked();
});
test('reserved debt is displayed but a second full-debt payment cannot be confirmed',async({page})=>{
    const user=fixture();await login(page,user);
    await page.route('**/api/v1/tuition/'+user.mssv,async route=>{
        const response=await route.fetch(),data=await response.json();data.invoices[0].status='RESERVED';
        await route.fulfill({response,json:data});
    });
    await page.locator('#studentCode').fill(user.mssv);await expect(page.locator('#invoiceSelection')).toBeVisible();
    await page.locator('#acceptPaymentTerms').check();
    await expect(page.locator('#selectedTotal')).toHaveText('5.000.000,00 ₫');
    await expect(page.locator('#confirmSelectionButton')).toBeDisabled();
    await expect(page.locator('#eligibilityNotice')).toContainText('đang được giao dịch khác xử lý');
});
