"use strict";
(() => {
    const terminal = new Set(["SUCCEEDED", "FAILED", "REFUNDED"]);
    const labels = { PENDING_OTP: "Chờ xác thực", OTP_VERIFIED: "Đã xác thực", PROCESSING: "Đang xử lý", PENDING_RECONCILIATION: "Đang đối soát", SUCCEEDED: "Thành công", FAILED: "Không thành công", REFUNDED: "Đã hoàn tiền" };
    const invoiceLabels = { UNPAID: "Chưa đóng", RESERVED: "Đang xử lý", PAID: "Đã đóng" };
    const storageKey = "ibanking.pendingPayment"; // Only opaque IDs; never tokens, OTP, balances or personal data.
    const state = { epoch: 0, tuition: null, selection: new Set(), mode: "ALL_UNPAID", payment: null, intent: null, challenge: null, timer: null, poll: null, pollCount: 0, cursor: null, historyVersion: 0, restoreUser: null, busy: false, creating: false };
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
        finally { button.disabled = false; button.removeAttribute("aria-busy"); tick(); }
    }
    function remember(key) { try { sessionStorage.setItem(storageKey, JSON.stringify({ payment_id: key, user_id: currentUser.id })); } catch { /* History remains available if browser storage is disabled. */ } }
    function forget() { try { sessionStorage.removeItem(storageKey); } catch { } }
    function steps(index) { ["stepLookup", "stepConfirm", "stepOTP", "stepResult"].forEach((id, n) => { const item = byId(id); item.classList.toggle("done", n < index); if (n === index) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current"); }); }
    function badge(status, invoice = false) { return el("span", (invoice ? invoiceLabels : labels)[status] || status, "soft-badge " + (status === "FAILED" ? "error" : (["PROCESSING", "PENDING_RECONCILIATION", "RESERVED", "REFUNDED"].includes(status) ? "warning" : (["PENDING_OTP", "UNPAID"].includes(status) ? "neutral" : "")))); }
    function updatePayer() {
        const user = currentUser, account = currentAccount;
        const values = { payerFullName: user?.full_name, payerIdentity: user?.identity_number, payerPhone: user?.phone, payerEmail: user?.email, payerAccount: account?.account_number, payerBalance: account ? (balanceHidden ? "••••••••" : formatMoney(account.balance)) : null };
        Object.entries(values).forEach(([id, value]) => { byId(id).textContent = value || (user ? "Chưa cập nhật" : "—"); });
    }
    function lockLookup(locked) {
        byId("studentCode").disabled = locked;
        byId("lookupButton").disabled = locked;
        byId("confirmSelectionButton").disabled = locked || state.selection.size === 0;
        document.querySelectorAll("#invoiceSelection input").forEach(input => { input.disabled = locked || input.dataset.unavailable === "true"; });
    }
    function renderSelection() {
        const rows = byId("invoiceRows"); rows.replaceChildren();
        const invoices = state.tuition?.invoices || [];
        invoices.forEach(invoice => {
            const tr = el("tr"), select = el("td"), input = el("input");
            input.type = "checkbox"; input.checked = state.selection.has(invoice.id); input.disabled = invoice.status !== "UNPAID";
            input.dataset.unavailable = String(invoice.status !== "UNPAID"); input.setAttribute("aria-label", `Chọn học kỳ ${invoice.semester}`);
            input.addEventListener("change", () => { state.mode = "SELECTED"; document.querySelector('input[name="selectionMode"][value="SELECTED"]').checked = true; input.checked ? state.selection.add(invoice.id) : state.selection.delete(invoice.id); updateSelection(); });
            select.append(input); tr.append(select, el("td", invoice.semester), el("td", formatMoney(invoice.amount_due), "number")); const status = el("td"); status.append(badge(invoice.status, true)); tr.append(status); rows.append(tr);
        });
        byId("invoiceCount").textContent = `${invoices.filter(row => row.status === "UNPAID").length} hóa đơn chưa đóng`;
        updateSelection();
    }
    function updateSelection() {
        const selected = (state.tuition?.invoices || []).filter(row => state.selection.has(row.id));
        const total = selected.reduce((sum, row) => sum + cents(row.amount_due), 0n);
        byId("selectedTotal").textContent = formatMoney(decimal(total));
        byId("selectedCount").textContent = `Đã chọn ${selected.length} hóa đơn`;
        byId("confirmSelectionButton").disabled = !selected.length || !!state.intent || !!state.payment;
        byId("balanceWarning").hidden = !currentAccount || total <= cents(currentAccount.balance);
    }
    async function lookup() {
        notice("tuitionNotice");
        const code = byId("studentCode").value.trim();
        if (!code) return;
        state.tuition = null; state.selection.clear(); byId("invoiceSelection").hidden = true;
        const data = await api(`/api/v1/tuition/${encodeURIComponent(code)}`);
        state.tuition = data; state.mode = "ALL_UNPAID";
        state.selection = new Set(data.invoices.filter(row => row.status === "UNPAID").map(row => row.id));
        document.querySelector('input[name="selectionMode"][value="ALL_UNPAID"]').checked = true;
        byId("studentName").textContent = data.full_name; byId("studentMssv").textContent = `MSSV: ${data.mssv}`;
        byId("invoiceSelection").hidden = false; renderSelection();
        if (!state.selection.size) notice("tuitionNotice", "Hiện không có học phí có thể thanh toán. Các khoản đã đóng hoặc đang xử lý được hiển thị bên dưới.");
    }
    function showIntent(text) {
        byId("pendingIntentCard").hidden = false; byId("pendingIntentMessage").textContent = text;
        byId("pendingIntentReference").textContent = state.intent.key;
        lockLookup(true);
    }
    async function createIntent() {
        if (state.creating) return;
        if (!state.intent) {
            if (!state.tuition || !state.selection.size) return;
            const payload = { mssv: state.tuition.mssv, selection_mode: state.mode };
            if (state.mode === "SELECTED") payload.invoice_ids = [...state.selection].sort((a, b) => a - b);
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
        state.payment = payment; state.intent = null;
        byId("pendingIntentCard").hidden = true; byId("lookupCard").hidden = true; byId("paymentCard").hidden = false;
        byId("paymentReference").textContent = payment.payment_id; byId("paymentTotal").textContent = formatMoney(payment.total_amount);
        byId("paymentStatusBadge").replaceWith(Object.assign(badge(payment.status), { id: "paymentStatusBadge" }));
        snapshot(payment);
        const pendingOTP = payment.status === "PENDING_OTP", verified = payment.status === "OTP_VERIFIED";
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
    }
    function tick() {
        if (!state.challenge) return;
        const remaining = Math.max(0, Math.ceil((Date.parse(state.challenge.expires_at) - Date.now()) / 1000));
        const cooldown = Math.max(0, Math.ceil((state.challenge.resendAt - Date.now()) / 1000));
        byId("otpCountdown").textContent = remaining ? `Mã hết hạn sau ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "Mã đã hết hạn. Vui lòng gửi lại mã.";
        byId("resendOtpButton").disabled = cooldown > 0;
        byId("resendOtpButton").textContent = cooldown ? `Gửi lại sau ${cooldown}s` : "Gửi lại mã";
        byId("payButton").disabled = !remaining || state.busy;
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
    async function refreshPayment() {
        if (!state.payment) return;
        const payment = await api(`/api/v1/payments/${state.payment.payment_id}`);
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
    async function loadHistory(more = false) {
        const version = ++state.historyVersion;
        notice("historyNotice", "Đang lấy lịch sử giao dịch…");
        const cursor = more ? state.cursor : null;
        const result = await api("/api/v1/payments?limit=10" + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""));
        if (version !== state.historyVersion) return;
        if (!more) byId("historyRows").replaceChildren();
        result.items.forEach(payment => {
            const row = el("tr"), reference = el("td"); reference.append(el("span", date(payment.created_at)), el("code", payment.transaction_code, "muted"));
            const student = el("td"); student.append(el("span", payment.student_name), el("span", payment.mssv, "muted"));
            const status = el("td"); status.append(badge(payment.status));
            const detail = el("td"), button = el("button", "Xem", "small-button"); button.type = "button"; button.setAttribute("aria-label", `Xem giao dịch ${payment.transaction_code}`);
            button.addEventListener("click", () => { button.disabled = true; openPayment(payment.payment_id).catch(error => { if (!error.stale) showMessage(error.message, true); }).finally(() => { button.disabled = false; }); }); detail.append(button);
            row.append(reference, student, el("td", formatMoney(payment.total_amount), "number"), status, detail); byId("historyRows").append(row);
        });
        state.cursor = result.next_cursor; byId("moreHistoryButton").hidden = !state.cursor;
        byId("historyEmpty").hidden = byId("historyRows").children.length > 0; notice("historyNotice");
    }
    function reset() {
        state.epoch += 1; state.historyVersion += 1; clearInterval(state.timer); clearTimeout(state.poll);
        Object.assign(state, { tuition: null, selection: new Set(), mode: "ALL_UNPAID", payment: null, intent: null, challenge: null, timer: null, poll: null, pollCount: 0, cursor: null, restoreUser: null, busy: false, creating: false });
        ["studentCode", "otpCode"].forEach(id => { byId(id).value = ""; });
        ["invoiceRows", "historyRows", "paymentSnapshot"].forEach(id => byId(id).replaceChildren());
        ["studentName", "studentMssv", "paymentReference", "paymentTotal", "otpDelivery", "resultTitle", "resultMessage", "receiptMessage", "pendingIntentReference"].forEach(id => { byId(id).textContent = ""; });
        byId("selectedTotal").textContent = "0,00 ₫"; byId("selectedCount").textContent = "Chưa chọn hóa đơn"; byId("invoiceCount").textContent = "";
        ["invoiceSelection", "paymentCard", "paymentResult", "pendingIntentCard", "otpForm", "historyEmpty", "moreHistoryButton"].forEach(id => { byId(id).hidden = true; });
        byId("lookupCard").hidden = false; notice("tuitionNotice"); notice("historyNotice"); lockLookup(false); steps(0);
        ["payerFullName", "payerIdentity", "payerPhone", "payerEmail", "payerAccount", "payerBalance"].forEach(id => { byId(id).textContent = "—"; });
    }
    function startAnother() {
        if (state.payment && !terminal.has(state.payment.status)) return;
        forget(); reset(); updatePayer(); byId("studentCode").focus();
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
    byId("tuitionLookupForm").addEventListener("submit", event => { event.preventDefault(); action("lookupButton", async () => { try { await lookup(); } catch (error) { if (!error.stale) notice("tuitionNotice", error.message, true); throw error; } }); });
    document.querySelectorAll('input[name="selectionMode"]').forEach(input => input.addEventListener("change", () => { state.mode = input.value; if (state.mode === "ALL_UNPAID") state.selection = new Set(state.tuition.invoices.filter(row => row.status === "UNPAID").map(row => row.id)); renderSelection(); }));
    byId("confirmSelectionButton").addEventListener("click", () => action("confirmSelectionButton", createIntent));
    byId("retryIntentButton").addEventListener("click", () => action("retryIntentButton", createIntent));
    byId("sendOtpButton").addEventListener("click", () => action("sendOtpButton", sendOTP));
    byId("resendOtpButton").addEventListener("click", () => action("resendOtpButton", sendOTP));
    byId("otpForm").addEventListener("submit", event => { event.preventDefault(); action("payButton", pay); });
    byId("resumeProcessButton").addEventListener("click", () => action("resumeProcessButton", pay));
    byId("checkPaymentButton").addEventListener("click", () => action("checkPaymentButton", async () => { state.pollCount = 0; await refreshPayment(); }));
    byId("newPaymentButton").addEventListener("click", startAnother);
    byId("copyPaymentButton").addEventListener("click", () => action("copyPaymentButton", async () => { await navigator.clipboard.writeText(state.payment.payment_id); showMessage("Đã sao chép mã giao dịch."); }));
    byId("reloadHistoryButton").addEventListener("click", () => action("reloadHistoryButton", () => loadHistory()));
    byId("moreHistoryButton").addEventListener("click", () => action("moreHistoryButton", () => loadHistory(true)));
    ["tuitionNav", "startTuitionButton"].forEach(id => byId(id).addEventListener("click", () => switchView("tuition")));
    ["historyNav", "resultHistoryButton"].forEach(id => byId(id).addEventListener("click", () => switchView("history")));
    window.tuitionUI = { reset, forget, enter, updatePayer };
})();
