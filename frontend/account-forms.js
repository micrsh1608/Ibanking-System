"use strict";
(() => {
    let editing = false, proofBusy = false, challenge = null, timer = null;
    function deliveryNotice(element, channel = currentUser?.email_delivery, recipient = currentUser?.email) {
        if (!element) return;
        const signature = JSON.stringify([channel, recipient]);
        if (element.dataset.delivery === signature) return;
        element.dataset.delivery = signature; element.hidden = false; element.replaceChildren();
        element.textContent = channel === "smtp"
            ? `Email nhận mã: ${recipient || "địa chỉ đã xác minh trong hồ sơ"}. Khi đổi email, hoàn tất xác minh địa chỉ mới trước khi thanh toán. Kiểm tra cả thư rác nếu chưa thấy thư.`
            : "Chưa cấu hình dịch vụ gửi email cho tài khoản này.";
    }
    function tick() {
        if (!challenge) return;
        const remaining = Math.max(0, Math.ceil((Date.parse(challenge.expires_at) - Date.now()) / 1000));
        const cooldown = Math.max(0, Math.ceil((challenge.resendAt - Date.now()) / 1000));
        byId("emailProofCountdown").textContent = remaining ? `Mã hết hạn sau ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "Mã xác minh đã hết hạn. Nhập mật khẩu và yêu cầu mã mới.";
        byId("confirmEmailButton").disabled = proofBusy || !remaining || !/^[0-9]{6}$/.test(byId("emailVerificationCode").value.trim());
        byId("resendEmailButton").disabled = proofBusy || cooldown > 0 || !byId("emailResendPassword").value;
        byId("resendEmailButton").textContent = cooldown ? `Gửi lại sau ${cooldown}s` : "Gửi lại mã xác minh email";
        byId("cancelEmailButton").disabled = proofBusy;
    }
    function syncProfile() {
        if (!currentUser) return;
        deliveryNotice(byId("profileMailNotice"), currentUser.email_delivery, currentUser.pending_email || currentUser.email);
        if (!editing) for (const [id, field] of [["profileFullName","full_name"],["profileEmail","email"],["profilePhone","phone"],["profileIdentity","identity_number"]]) byId(id).value = currentUser[field] || "";
        byId("profileEmailStatus").textContent = currentUser.email_verified ? "Email đang dùng đã được xác minh." : "Email chưa được xác minh. Cần xác minh trước khi thanh toán học phí.";
        byId("verifyCurrentEmailButton").hidden = currentUser.email_verified || !!currentUser.email_verification;
        const metadata = currentUser.email_verification;
        byId("emailVerificationPanel").hidden = !metadata;
        clearInterval(timer); timer = null;
        if (metadata) {
            if (challenge?.challenge_id !== metadata.challenge_id) byId("emailVerificationCode").value = "";
            challenge = { ...metadata, resendAt: Date.now() + metadata.resend_after_seconds * 1000 };
            byId("pendingEmailAddress").textContent = currentUser.pending_email;
            timer = setInterval(tick, 1000); tick();
        } else { challenge = null; byId("pendingEmailAddress").textContent = ""; }
    }
    function closeEditor() {
        editing = false; byId("profileForm").hidden = true; byId("editProfileButton").hidden = false; byId("profilePassword").value = "";
    }
    function reset() {
        closeEditor(); clearInterval(timer); timer = null; challenge = null; proofBusy = false;
        byId("profileForm").reset(); byId("emailVerificationForm").reset(); byId("emailResendPassword").value = "";
        byId("emailVerificationPanel").hidden = true; byId("profileEmailStatus").textContent = ""; byId("pendingEmailAddress").textContent = "";
        byId("verifyCurrentEmailButton").hidden = true;
    }
    function editProfile() { syncProfile(); editing = true; byId("profileForm").hidden = false; byId("editProfileButton").hidden = true; byId("profileEmail").focus(); }
    function showProofEntry() {
        if (!challenge || currentView !== "profile") return;
        byId("emailVerificationPanel").scrollIntoView({ behavior: "smooth", block: "start" });
        byId("emailVerificationCode").focus({ preventScroll: true });
    }
    function applyProfile(result) {
        renderUser(result); renderBalance();
    }
    async function recoverProfile(tokenUsed) {
        try {
            const result = await request('/users/me', { headers: { Authorization: `Bearer ${tokenUsed}` } });
            if (accessToken !== tokenUsed) return false;
            applyProfile(result); showProofEntry();
            return !!result.email_verification;
        } catch { return false; }
    }
    async function handleError(error, tokenUsed) {
        if (accessToken !== tokenUsed) return;
        if (error.status === 401) { clearSession(); byId("username").focus(); showMessage("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", true); return; }
        if (error.status === 403) {
            try { await loadAccount(); } catch (authError) { if (!accessToken) { showMessage(authError.message, true); return; } }
        }
        if (accessToken === tokenUsed) showMessage(error.message, true);
    }
    byId("editProfileButton").addEventListener("click", editProfile);
    byId("verifyCurrentEmailButton").addEventListener("click", editProfile);
    byId("cancelProfileButton").addEventListener("click", () => { closeEditor(); syncProfile(); byId("editProfileButton").focus(); });
    byId("profileForm").addEventListener("submit", async event => {
        event.preventDefault(); const button = byId("saveProfileButton"); if (button.disabled || !accessToken) return;
        const tokenUsed = accessToken;
        button.disabled = true; button.setAttribute("aria-busy", "true"); byId("cancelProfileButton").disabled = true; showMessage("");
        try {
            const result = await request("/users/me", { method: "PUT", headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenUsed}` }, body: JSON.stringify({
                full_name: byId("profileFullName").value.trim(), email: byId("profileEmail").value.trim(), phone: byId("profilePhone").value.trim() || null,
                identity_number: byId("profileIdentity").value.trim() || null, current_password: byId("profilePassword").value
            }) });
            if (accessToken !== tokenUsed) return;
            closeEditor();
            applyProfile(result);
            showMessage(result.email_verification ? "Hồ sơ đang chờ xác minh. Nhập mã gửi tới email bạn vừa nhập vào ô bên dưới để xác nhận và lưu." : "Đã lưu hồ sơ.");
            if (result.email_verification) showProofEntry();
        } catch (error) {
            if (accessToken === tokenUsed && (error.status === undefined || error.status >= 500)) {
                if (await recoverProfile(tokenUsed)) { closeEditor(); showMessage("Đã khôi phục yêu cầu chờ. Nhập mã đã nhận vào ô xác minh email để tiếp tục."); return; }
            }
            await handleError(error, tokenUsed);
        }
        finally { byId("profilePassword").value = ""; button.disabled = false; button.removeAttribute("aria-busy"); byId("cancelProfileButton").disabled = false; }
    });
    async function proofRequest(action, body, success) {
        if (proofBusy || !accessToken || !challenge) return;
        const tokenUsed = accessToken;
        proofBusy = true; tick(); showMessage("");
        try {
            const result = await request('/users/me/email-verification' + action, { method: action ? 'POST' : 'DELETE', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenUsed}` }, ...(body ? {body: JSON.stringify(body)} : {}) });
            if (accessToken === tokenUsed) { applyProfile(result); showMessage(success); }
        } catch (error) { await handleError(error, tokenUsed); }
        finally { proofBusy = false; byId("emailVerificationCode").value = ""; byId("emailResendPassword").value = ""; tick(); }
    }
    byId("emailVerificationCode").addEventListener("input", tick);
    byId("emailResendPassword").addEventListener("input", tick);
    byId("emailVerificationForm").addEventListener("submit", event => { event.preventDefault(); if (!byId("confirmEmailButton").disabled) proofRequest('/confirm', { challenge_id: challenge.challenge_id, code: byId("emailVerificationCode").value.trim() }, 'Đã xác minh email và lưu hồ sơ. Bạn có thể nhận OTP thanh toán tại địa chỉ này.'); });
    byId("resendEmailButton").addEventListener("click", () => { if (!byId("resendEmailButton").disabled) proofRequest('/resend', { current_password: byId("emailResendPassword").value }, 'Đã yêu cầu mã xác minh mới. Mã cũ không còn hiệu lực.'); });
    byId("cancelEmailButton").addEventListener("click", () => proofRequest('', null, 'Đã hủy yêu cầu; hồ sơ và email đang dùng được giữ nguyên.'));
    window.accountForms = { reset, syncProfile, deliveryNotice };
})();
