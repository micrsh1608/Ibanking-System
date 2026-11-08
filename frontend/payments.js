"use strict";
(() => {
    const terminal = new Set(["SUCCEEDED", "FAILED", "REFUNDED"]);
    const labels = { PENDING_OTP: "Chờ xác thực", OTP_VERIFIED: "Đã xác thực", PROCESSING: "Đang xử lý", PENDING_RECONCILIATION: "Đang đối soát", SUCCEEDED: "Thành công", FAILED: "Không thành công", REFUNDED: "Đã hoàn tiền" };
    const invoiceLabels = { UNPAID: "Chưa đóng", RESERVED: "Đang xử lý", PAID: "Đã đóng" };
    const storageKey = "ibanking.pendingPayment"; // Only opaque IDs; never tokens, OTP, balances or personal data.
    const state = { epoch: 0, tuition: null, selection: new Set(), payment: null, intent: null, challenge: null, timer: null, poll: null, pollCount: 0, cursor: null, historyVersion: 0, historyPages: 0, historySignature: null, restoreUser: null, busy: false, creating: false, lookupVersion: 0, lookupCode: null, lookupBusy: false, lookupTimer: null, payerSignature: null, debtChanged: false };
    const el = (tag, text, className) => { const item = document.createElement(tag); if (text !== undefined) item.textContent = String(text); if (className) item.className = className; return item; };
    const date = value => value ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Ho_Chi_Minh" }).format(new Date(value)) : "—";
    const cents = value => { const [integer, fraction = ""] = String(value).split("."); return BigInt(integer) * 100n + BigInt(fraction.padEnd(2, "0").slice(0, 2)); };
    const decimal = value => `${value / 100n}.${String(value % 100n).padStart(2, "0")}`;
    const stale = () => Object.assign(new Error("Phiên đã thay đổi"), { stale: true });
    function notice(id, text = "", error = false) { const item = byId(id); item.textContent = text; item.hidden = !text; item.classList.toggle("error", error); item.setAttribute("role", error ? "alert" : "status"); }
    async function api(path, options = {}) {
        const token = accessToken, epoch = state.epoch;
        if (!token) throw stale();
        try {
            const data = await request(path, { ...options, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers } });
            if (token !== accessToken || epoch !== state.epoch) throw stale();
            return data;
        } catch (error) {
            if (token !== accessToken || epoch !== state.epoch) throw stale();
            if (error.status === 401 || error.status === 403) { clearSession(); showMessage("Phiên đăng nhập đã kết thúc. Vui lòng đăng nhập lại.", true); throw stale(); }
            throw error;
        }
    }
    async function action(buttonId, task) {
        const button = byId(buttonId);
        if (button.disabled) return;
        button.disabled = true; button.setAttribute("aria-busy", "true");
        try { await task(); } catch (error) { if (!error.stale) showMessage(error.message, true); }
        finally { button.disabled = false; button.removeAttribute("aria-busy"); syncControls(); tick(); }
    }
    function remember(key) { try { sessionStorage.setItem(storageKey, JSON.stringify({ payment_id: key, user_id: currentUser.id })); } catch { /* History remains available if browser storage is disabled. */ } }
    function forget() { try { sessionStorage.removeItem(storageKey); } catch { } }
    function steps(index) { ["stepLookup", "stepConfirm", "stepOTP", "stepResult"].forEach((id, n) => { const item = byId(id); item.classList.toggle("done", n < index); if (n === index) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current"); }); }
    function badge(status, invoice = false) { return el("span", (invoice ? invoiceLabels : labels)[status] || status, "soft-badge " + (status === "FAILED" ? "error" : (["PROCESSING", "PENDING_RECONCILIATION", "RESERVED", "REFUNDED"].includes(status) ? "warning" : (["PENDING_OTP", "UNPAID"].includes(status) ? "neutral" : "")))); }
    function updatePayer() {
        const user = currentUser, account = currentAccount;
        const balance = account ? (balanceHidden ? "••••••••" : formatMoney(account.balance)) : null;
        const values = { payerFullName: user?.full_name, payerIdentity: user?.identity_number, payerPhone: user?.phone, payerEmail: user?.email, payerAccount: account?.account_number, payerBalance: balance, availableBalance: balance };
        Object.entries(values).forEach(([id, value]) => { byId(id).textContent = value || (user ? "Chưa cập nhật" : "—"); });
        const signature = JSON.stringify([user?.id, user?.full_name, user?.phone, user?.email, user?.email_verified, user?.email_delivery, account?.id]);
        if (state.payerSignature && state.payerSignature !== signature) byId("acceptPaymentTerms").checked = false;
        state.payerSignature = signature;
        notice("payerDetailsWarning", payerIssue()); byId("payerProfileButton").hidden = !payerIssue();
        syncControls();
    }
    function payerIssue() {
        if (!currentUser || !currentAccount) return "Vui lòng đăng nhập để thanh toán.";
        if (currentUser.email_verified !== true) return "Email chưa được xác minh. Vào Thông tin cá nhân để xác minh trước khi thanh toán.";
        const digits = (currentUser.phone || "").replace(/\D/g, "").length;
        if (!currentUser.full_name?.trim() || !/^[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+$/.test(currentUser.email || "") || !/^[+0-9 ()-]{7,20}$/.test(currentUser.phone || "") || digits < 7 || digits > 15) return "Cần có đủ họ tên, số điện thoại và email hợp lệ trong hồ sơ trước khi thanh toán.";
        return "";
    }
    function selectionTotal() { return (state.tuition?.invoices || []).filter(row => row.status !== "PAID").reduce((sum, row) => sum + cents(row.amount_due), 0n); }
    function eligibilityIssue() {
        if (payerIssue()) return payerIssue();
        if (currentAccount.status !== "ACTIVE") return "Tài khoản đang khóa hoặc chưa hoạt động.";
        if (!state.tuition || state.lookupCode !== byId("studentCode").value.trim()) return "Vui lòng tra cứu MSSV trước khi xác nhận.";
        if (state.tuition.invoices.some(row => row.status === "RESERVED")) return "Công nợ đang được giao dịch khác xử lý. Vui lòng chờ kết quả rồi tra cứu lại.";
        if (selectionTotal() <= 0n) return "MSSV này không còn học phí chưa đóng để thanh toán.";
        if (cents(currentAccount.balance) < selectionTotal()) return "Số dư khả dụng không đủ để thanh toán toàn bộ công nợ.";
        if (!byId("acceptPaymentTerms").checked) return "Đọc và đồng ý điều khoản trước khi xác nhận giao dịch.";
        return "";
    }
    function legacyDraft(payment) { return payment && ["PENDING_OTP", "OTP_VERIFIED"].includes(payment.status) && (payment.selection_mode !== "ALL_UNPAID" || !payment.terms_accepted_at || (!!currentUser && (payment.payer_email !== currentUser.email || (!!payment.email_delivery && !!currentUser.email_delivery && payment.email_delivery !== currentUser.email_delivery)))); }
    function draftIssue() {
        if (!state.payment || !["PENDING_OTP", "OTP_VERIFIED"].includes(state.payment.status)) return "";
        if (state.debtChanged) return "Công nợ đã thay đổi hoặc đang được giao dịch khác xử lý. Hủy giao dịch chờ và tra cứu lại trước khi thanh toán.";
        if (currentAccount && cents(currentAccount.balance) < cents(state.payment.total_amount)) return "Số dư đã thay đổi và không còn đủ cho giao dịch này. Bạn có thể hủy giao dịch chờ để tra cứu lại.";
        return "";
    }
    function syncControls() {
        const locked = !!state.intent || !!state.payment || state.creating;
        byId("studentCode").disabled = locked;
        byId("lookupButton").disabled = locked || state.lookupBusy || !byId("studentCode").value.trim();
        byId("acceptPaymentTerms").disabled = locked || state.lookupBusy || !state.tuition || selectionTotal() <= 0n;
        byId("confirmSelectionButton").disabled = locked || state.lookupBusy || !!eligibilityIssue();
        byId("balanceWarning").hidden = !currentAccount || !state.tuition || selectionTotal() <= cents(currentAccount.balance);
        notice("eligibilityNotice", state.tuition && !locked ? eligibilityIssue() : "");
        const invalid = !state.payment || !!payerIssue() || currentAccount?.status !== "ACTIVE" || !!draftIssue() || legacyDraft(state.payment);
        for (const id of ["sendOtpButton", "resumeProcessButton"]) byId(id).disabled = invalid || state.busy || byId(id).getAttribute("aria-busy") === "true";
        byId("cancelDraftButton").disabled = state.busy || state.creating || byId("cancelDraftButton").getAttribute("aria-busy") === "true";
        notice("paymentEligibilityNotice", draftIssue(), true);
    }
    function lockLookup(locked) {
        syncControls();
    }
    function renderSelection() {
        const rows = byId("invoiceRows"); rows.replaceChildren();
        const invoices = state.tuition?.invoices || [];
        invoices.forEach(invoice => {
            const tr = el("tr"); tr.append(el("td", invoice.semester), el("td", formatMoney(invoice.amount_due), "number")); const status = el("td"); status.append(badge(invoice.status, true)); tr.append(status); rows.append(tr);
        });
        byId("invoiceCount").textContent = `${invoices.filter(row => row.status !== "PAID").length} hóa đơn chưa hoàn tất`;
        updateSelection();
    }
    function updateSelection() {
        byId("selectedTotal").textContent = formatMoney(decimal(selectionTotal()));
        byId("selectedCount").textContent = `${(state.tuition?.invoices || []).filter(row => row.status !== "PAID").length} hóa đơn chưa hoàn tất`;
        syncControls();
    }
    function invalidateLookup() {
        clearTimeout(state.lookupTimer); state.lookupVersion += 1; state.lookupBusy = false; state.lookupCode = null;
        state.tuition = null; state.selection.clear(); byId("invoiceSelection").hidden = true; byId("acceptPaymentTerms").checked = false;
        byId("studentName").textContent = byId("studentMssv").textContent = ""; byId("invoiceRows").replaceChildren();
        byId("selectedTotal").textContent = "0,00 ₫"; notice("tuitionNotice"); syncControls();
    }
    async function lookup() {
        clearTimeout(state.lookupTimer);
        const code = byId("studentCode").value.trim();
        if (!code || state.intent || state.payment) return;
        invalidateLookup(); const version = ++state.lookupVersion; state.lookupBusy = true; syncControls(); notice("tuitionNotice", "Đang tra cứu học phí và số dư khả dụng…");
        try {
            if (!await loadAccount()) return;
            if (version !== state.lookupVersion || code !== byId("studentCode").value.trim()) return;
            const data = await api(`/api/v1/tuition/${encodeURIComponent(code)}`);
            if (version !== state.lookupVersion || code !== byId("studentCode").value.trim()) return;
            state.tuition = data; state.lookupCode = code;
            state.selection = new Set(data.invoices.filter(row => row.status === "UNPAID").map(row => row.id));
            byId("studentName").textContent = data.full_name; byId("studentMssv").textContent = `MSSV: ${data.mssv}`;
            byId("invoiceSelection").hidden = false; renderSelection(); notice("tuitionNotice");
        } catch (error) { if (!error.stale && version === state.lookupVersion) notice("tuitionNotice", error.message, true); }
        finally { if (version === state.lookupVersion) { state.lookupBusy = false; syncControls(); } }
    }
    function showIntent(text) {
        byId("pendingIntentCard").hidden = false; byId("pendingIntentMessage").textContent = text;
        byId("pendingIntentReference").textContent = state.intent.key;
        lockLookup(true);
    }
    async function createIntent() {
        if (state.creating) return;
        if (!state.intent) {
            const issue = eligibilityIssue();
            if (issue) { notice("tuitionNotice", issue, true); syncControls(); return; }
            const payload = { mssv: state.tuition.mssv, selection_mode: "ALL_UNPAID", terms_accepted: true };
            state.intent = { key: crypto.randomUUID(), payload };
            remember(state.intent.key);
        }
        const epoch = state.epoch;
        state.creating = true; byId("retryIntentButton").disabled = true;
        showIntent("Đang xác nhận danh sách và tổng tiền. Nếu kết nối bị gián đoạn, hãy thử lại bằng đúng mã này.");
        try {
            const result = await api("/api/v1/payments", { method: "POST", headers: { "Idempotency-Key": state.intent.key }, body: JSON.stringify(state.intent.payload) });
            if (!result.payment_id) throw new Error("Chưa nhận được kết quả tạo giao dịch. Thử lại bằng mã hiện tại.");
            state.intent = null; byId("pendingIntentCard").hidden = true; renderPayment(result);
            byId("paymentCard").scrollIntoView({ behavior: "smooth", block: "start" });
            if (result.status === "PENDING_OTP" && !result.active_challenge && !legacyDraft(result)) {
                await action("sendOtpButton", sendOTP);
            }
        } catch (error) {
            if (error.stale) throw error;
            if ([400, 404, 422].includes(error.status) || (error.status === 409 && !error.message.startsWith("Giao dịch đang"))) {
                state.intent = null; forget(); byId("pendingIntentCard").hidden = true; lockLookup(false); notice("tuitionNotice", error.message + ". Vui lòng tra cứu lại học phí.", true);
            } else showIntent("Chưa xác định được kết quả tạo giao dịch. Thử lại sẽ sử dụng cùng mã, không tạo khoản thanh toán mới.");
            throw error;
        } finally {
            if (epoch === state.epoch) { state.creating = false; byId("retryIntentButton").disabled = false; lockLookup(!!state.intent || !!state.payment); }
        }
    }
    function snapshot(payment) {
        const container = byId("paymentSnapshot"); container.replaceChildren();
        const person = el("div", undefined, "snapshot-student"); person.append(el("strong", payment.student_name), el("span", `MSSV: ${payment.mssv}`)); container.append(person);
        payment.items.forEach(item => { const line = el("div", undefined, "snapshot-line"); line.append(el("span", item.semester), el("strong", formatMoney(item.amount))); container.append(line); });
    }
    function renderPayment(payment) {
        const previous = state.payment;
        if (previous?.payment_id !== payment.payment_id) state.debtChanged = false;
        state.payment = payment; state.intent = null;
        byId("pendingIntentCard").hidden = true; byId("lookupCard").hidden = true; byId("paymentCard").hidden = false;
        byId("paymentReference").textContent = payment.payment_id; byId("paymentTotal").textContent = formatMoney(payment.total_amount);
        byId("paymentStatusBadge").replaceWith(Object.assign(badge(payment.status), { id: "paymentStatusBadge" }));
        snapshot(payment);
        byId("confirmationHint").textContent = `Thanh toán toàn bộ các hóa đơn đã xác nhận. Điều khoản ${payment.terms_version || "chưa xác nhận"}.`;
        const pendingOTP = payment.status === "PENDING_OTP", verified = payment.status === "OTP_VERIFIED";
        window.accountForms?.deliveryNotice(byId("paymentMailNotice"), payment.email_delivery || currentUser?.email_delivery, payment.payer_email);
        if (pendingOTP && payment.active_challenge) {
            if (state.challenge?.challenge_id !== payment.active_challenge.challenge_id) {
                state.challenge = { ...payment.active_challenge, resendAt: Date.now() + payment.active_challenge.resend_after_seconds * 1000 };
                byId("otpCode").value = "";
            }
            byId("otpDelivery").textContent = `Nhập mã được gửi đến ${state.challenge.delivery_address}.`;
            if (!state.timer) state.timer = setInterval(tick, 1000);
            tick();
        } else {
            state.challenge = null; clearInterval(state.timer); state.timer = null;
        }
        byId("paymentCardTitle").textContent = terminal.has(payment.status) ? "Chi tiết giao dịch" : "Kiểm tra trước khi xác thực";
        byId("sendOtpButton").hidden = (!pendingOTP && !verified) || (pendingOTP && !!state.challenge);
        byId("sendOtpButton").textContent = verified ? "Gửi mã mới qua email" : "Gửi mã xác thực qua email";
        byId("otpForm").hidden = !pendingOTP || !state.challenge;
        byId("resumeProcessButton").hidden = !verified;
        byId("confirmationHint").hidden = !pendingOTP && !verified;
        if (pendingOTP) { steps(state.challenge ? 2 : 1); byId("paymentResult").hidden = true; }
        else if (verified) { steps(2); byId("paymentResult").hidden = true; }
        else {
            steps(3); byId("paymentResult").hidden = false;
            const done = terminal.has(payment.status), success = payment.status === "SUCCEEDED";
            byId("paymentResult").classList.toggle("pending", !done); byId("paymentResult").classList.toggle("failed", done && !success);
            byId("resultSymbol").textContent = success ? "✓" : (done ? "!" : "…");
            byId("resultEyebrow").textContent = success ? "CẢM ƠN BẠN ĐÃ THANH TOÁN" : (done ? "KẾT QUẢ GIAO DỊCH" : "VUI LÒNG GIỮ MÃ GIAO DỊCH");
            byId("resultTitle").textContent = labels[payment.status] || "Đang cập nhật";
            byId("resultMessage").textContent = success ? `Đã thanh toán ${formatMoney(payment.total_amount)} cho ${payment.student_name}. Tất cả hóa đơn trong giao dịch đã được ghi nhận.` : (payment.status === "REFUNDED" ? "Giao dịch chưa hoàn tất. Số tiền đã được hoàn về tài khoản. " + (payment.error_message || "") : (payment.status === "FAILED" ? "Giao dịch chưa hoàn tất, tài khoản không bị trừ tiền. " + (payment.error_message || "") : "Hệ thống đang xác nhận kết quả với các dịch vụ. Không tạo giao dịch mới cho các hóa đơn này. Bạn có thể kiểm tra lại bằng mã hiện tại."));
            byId("receiptMessage").textContent = success ? (payment.receipt_status === "SENT" ? "Biên nhận đã được gửi đến email của bạn." : (payment.receipt_status === "PENDING" ? "Biên nhận đang được gửi qua email. Việc gửi lại email sẽ không trừ tiền thêm." : "Xem danh sách hóa đơn đã thanh toán trong giao dịch này.")) : "";
            byId("newPaymentButton").hidden = !done;
        }
        if (terminal.has(payment.status)) {
            forget(); clearTimeout(state.poll); state.poll = null; clearInterval(state.timer); state.timer = null; state.challenge = null;
            if (previous?.status !== payment.status) loadAccount().catch(error => { if (accessToken) showMessage(error.message, true); });
            if (payment.status === "SUCCEEDED" && payment.receipt_status === "PENDING") schedulePoll();
        } else {
            remember(payment.payment_id);
            if (["PROCESSING", "PENDING_RECONCILIATION"].includes(payment.status)) schedulePoll();
        }
        if (legacyDraft(payment)) {
            byId("sendOtpButton").hidden = byId("otpForm").hidden = byId("resumeProcessButton").hidden = true;
            byId("paymentResult").hidden = false; byId("newPaymentButton").hidden = false;
            byId("resultTitle").textContent = "Cần xác nhận giao dịch mới";
            byId("resultMessage").textContent = "Giao dịch chờ dùng email hoặc thông tin xác nhận cũ. Tạo giao dịch mới để dùng email đã xác minh và xác nhận lại toàn bộ công nợ.";
            byId("paymentResult").classList.add("pending"); byId("paymentResult").classList.remove("failed");
            byId("resultSymbol").textContent = "!"; byId("resultEyebrow").textContent = "XÁC NHẬN LẠI CÔNG NỢ"; byId("receiptMessage").textContent = "";
        }
        byId("cancelDraftButton").hidden = !pendingOTP && !verified;
        syncControls();
    }
    function tick() {
        if (!state.challenge) return;
        const remaining = Math.max(0, Math.ceil((Date.parse(state.challenge.expires_at) - Date.now()) / 1000));
        const cooldown = Math.max(0, Math.ceil((state.challenge.resendAt - Date.now()) / 1000));
        byId("otpCountdown").textContent = remaining ? `Mã hết hạn sau ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "Mã đã hết hạn. Vui lòng gửi lại mã.";
        byId("resendOtpButton").disabled = cooldown > 0;
        byId("resendOtpButton").textContent = cooldown ? `Gửi lại sau ${cooldown}s` : "Gửi lại mã";
        byId("payButton").disabled = !remaining || state.busy || !/^[0-9]{6}$/.test(byId("otpCode").value.trim()) || !!payerIssue() || currentAccount?.status !== "ACTIVE" || !!draftIssue() || legacyDraft(state.payment);
    }
    async function sendOTP() {
        const key = state.payment.payment_id;
        state.challenge = null; byId("otpForm").hidden = true;
        try {
            const result = await api(`/api/v1/payments/${key}/send-otp`, { method: "POST" });
            state.challenge = { ...result, resendAt: Date.now() + result.resend_after_seconds * 1000 };
            byId("otpCode").value = ""; byId("otpDelivery").textContent = `Mã xác thực đã được gửi đến ${result.delivery_address}.`;
            state.payment.status = "PENDING_OTP"; state.payment.active_challenge = result; renderPayment(state.payment);
            clearInterval(state.timer); state.timer = setInterval(tick, 1000); tick(); byId("otpCode").focus();
        } catch (error) { if (!error.stale && state.payment) { try { await refreshPayment(); } catch (refreshError) { if (refreshError.stale) throw refreshError; renderPayment(state.payment); } } throw error; }
    }
    async function refreshPayment({ quiet = false } = {}) {
        if (!state.payment) return;
        const key = state.payment.payment_id;
        const payment = await api(`/api/v1/payments/${key}`);
        if (state.payment?.payment_id !== key || (quiet && state.busy)) return;
        renderPayment(payment);
    }
    function schedulePoll() {
        if (state.poll || state.pollCount >= 60) return;
        state.poll = setTimeout(async () => {
            state.poll = null; state.pollCount += 1;
            try { await refreshPayment(); } catch (error) { if (!error.stale && accessToken) { showMessage("Chưa lấy được kết quả. Giữ mã giao dịch và dùng nút kiểm tra lại trạng thái.", true); schedulePoll(); } }
        }, 2000);
    }
    async function pay() {
        if (!state.payment || state.busy) return;
        state.busy = true; byId("payButton").disabled = true;
        const key = state.payment.payment_id;
        try {
            if (state.payment.status !== "OTP_VERIFIED") {
                if (!state.challenge) throw new Error("Yêu cầu mã OTP trước khi thanh toán.");
                await api(`/api/v1/payments/${key}/verify-otp`, { method: "POST", body: JSON.stringify({ challenge_id: state.challenge.challenge_id, otp: byId("otpCode").value.trim() }) });
                state.payment.status = "OTP_VERIFIED";
            }
            const result = await api(`/api/v1/payments/${key}/process`, { method: "POST", allowStatuses: [409] });
            if (!result.payment_id) throw Object.assign(new Error(result.detail || "Chưa xử lý được giao dịch"), { status: 409 });
            renderPayment(result);
            if (!byId("paymentResult").hidden) byId("paymentResult").scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (error) {
            if (error.stale) throw error;
            try { await refreshPayment(); } catch (refreshError) { if (refreshError.stale) throw refreshError; }
            if (!state.payment || !terminal.has(state.payment.status)) throw error;
        } finally { state.busy = false; tick(); }
    }
    async function openPayment(key) {
        const payment = await api(`/api/v1/payments/${key}`);
        clearInterval(state.timer); clearTimeout(state.poll); state.poll = null; state.timer = null;
        state.challenge = null; state.pollCount = 0; renderPayment(payment); switchView("tuition");
    }
    async function loadHistory(more = false, quiet = false) {
        const version = ++state.historyVersion;
        if (!quiet) notice("historyNotice", "Đang lấy lịch sử giao dịch…");
        const cursor = more ? state.cursor : null;
        const result = await api("/api/v1/payments?limit=10" + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""));
        if (version !== state.historyVersion) return;
        const signature = JSON.stringify(result.items.map(row => [row.payment_id, row.status, row.updated_at, row.receipt_status]));
        if (quiet && signature === state.historySignature) return;
        if (!more) byId("historyRows").replaceChildren();
        result.items.forEach(payment => {
            const row = el("tr"), reference = el("td"); reference.append(el("span", date(payment.created_at)), el("code", payment.transaction_code, "muted"));
            const student = el("td"); student.append(el("span", payment.student_name), el("span", payment.mssv, "muted"));
            const status = el("td"); status.append(badge(payment.status));
            const detail = el("td"), button = el("button", "Xem", "small-button"); button.type = "button"; button.setAttribute("aria-label", `Xem giao dịch ${payment.transaction_code}`);
            button.addEventListener("click", () => { button.disabled = true; openPayment(payment.payment_id).catch(error => { if (!error.stale) showMessage(error.message, true); }).finally(() => { button.disabled = false; }); }); detail.append(button);
            row.dataset.paymentId = payment.payment_id;
            row.dataset.paymentStatus = payment.status;
            row.append(reference, student, el("td", formatMoney(payment.total_amount), "number"), status, detail); byId("historyRows").append(row);
        });
        state.cursor = result.next_cursor; byId("moreHistoryButton").hidden = !state.cursor;
        state.historyPages = more ? state.historyPages + 1 : 1;
        state.historySignature = more ? null : signature;
        byId("historyEmpty").hidden = byId("historyRows").children.length > 0; notice("historyNotice");
    }
    function reset() {
        state.epoch += 1; state.historyVersion += 1; state.lookupVersion += 1; clearInterval(state.timer); clearTimeout(state.poll); clearTimeout(state.lookupTimer);
        Object.assign(state, { tuition: null, selection: new Set(), payment: null, intent: null, challenge: null, timer: null, poll: null, pollCount: 0, cursor: null, historyPages: 0, historySignature: null, restoreUser: null, busy: false, creating: false, lookupCode: null, lookupBusy: false, lookupTimer: null, payerSignature: null, debtChanged: false });
        byId("acceptPaymentTerms").checked = false;
        ["studentCode", "otpCode"].forEach(id => { byId(id).value = ""; });
        ["invoiceRows", "historyRows", "paymentSnapshot"].forEach(id => byId(id).replaceChildren());
        ["studentName", "studentMssv", "paymentReference", "paymentTotal", "otpDelivery", "resultTitle", "resultMessage", "receiptMessage", "pendingIntentReference"].forEach(id => { byId(id).textContent = ""; });
        byId("selectedTotal").textContent = "0,00 ₫"; byId("selectedCount").textContent = "Chưa chọn hóa đơn"; byId("invoiceCount").textContent = "";
        ["invoiceSelection", "paymentCard", "paymentResult", "pendingIntentCard", "otpForm", "historyEmpty", "moreHistoryButton"].forEach(id => { byId(id).hidden = true; });
        byId("lookupCard").hidden = false; notice("tuitionNotice"); notice("historyNotice"); lockLookup(false); steps(0);
        ["payerFullName", "payerIdentity", "payerPhone", "payerEmail", "payerAccount", "payerBalance", "availableBalance"].forEach(id => { byId(id).textContent = "—"; });
    }
    async function startAnother() {
        if (state.busy || state.creating) return;
        if (state.payment && ["PENDING_OTP", "OTP_VERIFIED"].includes(state.payment.status)) {
            state.busy = true; syncControls(); tick();
            try { await api(`/api/v1/payments/${state.payment.payment_id}/cancel`, { method: "POST" }); }
            finally { state.busy = false; syncControls(); tick(); }
        } else if (state.payment && !terminal.has(state.payment.status)) return;
        forget(); reset(); updatePayer(); byId("studentCode").focus();
    }
    const tuitionSignature = data => JSON.stringify([data.mssv, data.full_name, data.invoices.map(row => [row.id, row.version, row.status, row.amount_due])]);
    async function refreshLive() {
        if (state.busy || state.creating || state.intent) return;
        if (currentView === "history") {
            if (state.historyPages <= 1) { await loadHistory(false, true); return; }
            const version = state.historyVersion;
            const rows = [...byId("historyRows").children];
            const pendingRows = rows.filter(row => !terminal.has(row.dataset.paymentStatus));
            await Promise.all(pendingRows.map(async row => {
                const payment = await api(`/api/v1/payments/${row.dataset.paymentId}`);
                if (version !== state.historyVersion || !row.isConnected) return;
                row.dataset.paymentStatus = payment.status;
                row.children[3].replaceChildren(badge(payment.status));
            }));
            return;
        }
        if (currentView !== "tuition" || state.lookupBusy) return;
        if (state.payment) {
            const key = state.payment.payment_id;
            if (!terminal.has(state.payment.status) && !state.poll) await refreshPayment({ quiet: true });
            if (state.payment?.payment_id !== key || !["PENDING_OTP", "OTP_VERIFIED"].includes(state.payment.status)) return;
            const data = await api(`/api/v1/tuition/${encodeURIComponent(state.payment.mssv)}`);
            if (state.busy || state.payment?.payment_id !== key || !["PENDING_OTP", "OTP_VERIFIED"].includes(state.payment.status)) return;
            const unpaid = data.invoices.filter(row => row.status === "UNPAID");
            state.debtChanged = data.invoices.some(row => row.status === "RESERVED") || unpaid.length !== state.payment.items.length || state.payment.items.some(item => !unpaid.some(row => row.id === item.invoice_id && row.version === item.invoice_version && cents(row.amount_due) === cents(item.amount)));
            syncControls(); tick();
            return;
        }
        const code = state.lookupCode, version = state.lookupVersion;
        if (!code || code !== byId("studentCode").value.trim() || !state.tuition) return;
        const data = await api(`/api/v1/tuition/${encodeURIComponent(code)}`);
        if (state.payment || version !== state.lookupVersion || code !== byId("studentCode").value.trim()) return;
        if (tuitionSignature(data) !== tuitionSignature(state.tuition)) {
            state.tuition = data; byId("acceptPaymentTerms").checked = false;
            byId("studentName").textContent = data.full_name; renderSelection();
            notice("tuitionNotice", "Công nợ vừa được cập nhật. Kiểm tra lại thông tin trước khi xác nhận.");
        }
    }
    function enter(view) {
        updatePayer();
        if (view === "history") loadHistory().catch(error => { if (!error.stale) notice("historyNotice", error.message, true); });
        if (currentUser && state.restoreUser !== currentUser.id) {
            state.restoreUser = currentUser.id;
            try {
                const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
                if (saved?.user_id === currentUser.id && /^[0-9a-f-]{36}$/i.test(saved.payment_id)) openPayment(saved.payment_id).catch(error => { if (!error.stale && error.status !== 404) showMessage("Bạn có thể tìm giao dịch đang chờ trong Lịch sử.", true); });
            } catch { /* Optional restoration only. */ }
        }
    }
    byId("tuitionLookupForm").addEventListener("submit", event => { event.preventDefault(); lookup(); });
    byId("studentCode").addEventListener("input", () => { if (state.intent || state.payment) return; invalidateLookup(); if (byId("studentCode").value.trim()) state.lookupTimer = setTimeout(lookup, 650); });
    byId("acceptPaymentTerms").addEventListener("change", syncControls);
    byId("otpCode").addEventListener("input", tick);
    byId("payerProfileButton").addEventListener("click", () => switchView("profile"));
    byId("confirmSelectionButton").addEventListener("click", () => action("confirmSelectionButton", createIntent));
    byId("retryIntentButton").addEventListener("click", () => action("retryIntentButton", createIntent));
    byId("sendOtpButton").addEventListener("click", () => action("sendOtpButton", sendOTP));
    byId("resendOtpButton").addEventListener("click", () => action("resendOtpButton", sendOTP));
    byId("otpForm").addEventListener("submit", event => { event.preventDefault(); action("payButton", pay); });
    byId("resumeProcessButton").addEventListener("click", () => action("resumeProcessButton", pay));
    byId("checkPaymentButton").addEventListener("click", () => action("checkPaymentButton", async () => { state.pollCount = 0; await refreshPayment(); }));
    byId("newPaymentButton").addEventListener("click", () => action("newPaymentButton", startAnother));
    byId("cancelDraftButton").addEventListener("click", () => action("cancelDraftButton", startAnother));
    byId("copyPaymentButton").addEventListener("click", () => action("copyPaymentButton", async () => { await navigator.clipboard.writeText(state.payment.payment_id); showMessage("Đã sao chép mã giao dịch."); }));
    byId("reloadHistoryButton").addEventListener("click", () => action("reloadHistoryButton", () => loadHistory()));
    byId("moreHistoryButton").addEventListener("click", () => action("moreHistoryButton", () => loadHistory(true)));
    ["tuitionNav", "startTuitionButton"].forEach(id => byId(id).addEventListener("click", () => switchView("tuition")));
    ["historyNav", "resultHistoryButton"].forEach(id => byId(id).addEventListener("click", () => switchView("history")));
    window.tuitionUI = { reset, forget, enter, updatePayer, refreshLive, isBusy: () => state.busy || state.creating || state.lookupBusy };
})();
