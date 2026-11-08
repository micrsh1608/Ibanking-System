"use strict";
const byId = id => document.getElementById(id);
// Token chỉ nằm trong bộ nhớ; không ghi localStorage/sessionStorage.
let accessToken = null;
let currentUser = null;
let currentAccount = null;
let balanceHidden = false;
let currentView = "overview";
let messageTimer;
let accountLoadVersion = 0;
let liveRefreshing = false;
function showMessage(text, isError = false) {
    clearTimeout(messageTimer);
    const element = byId("message");
    element.textContent = text;
    element.classList.toggle("error", isError);
    element.setAttribute("role", isError ? "alert" : "status");
    element.hidden = !text;
    if (text && !isError) messageTimer = setTimeout(() => { element.hidden = true; }, 4500);
}
function initials(name) {
    return String(name || "").trim().split(/\s+/).slice(-2).map(part => Array.from(part)[0] || "").join("").toLocaleUpperCase("vi-VN");
}
function switchView(view, focus = true) {
    currentView = view;
    ["overview", "profile", "tuition", "history"].forEach(name => {
        byId(name + "Content").hidden = name !== view;
        const button = byId(name + "Nav");
        button.classList.toggle("active", name === view);
        if (name === view) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    });
    const titles = { overview: "Tổng quan", profile: "Thông tin cá nhân", tuition: "Đóng học phí", history: "Lịch sử giao dịch" };
    const subtitles = { overview: "Một góc nhìn rõ ràng về tài khoản của bạn.", profile: "Thông tin gắn liền với tài khoản của bạn.", tuition: "Từng học kỳ được an tâm. Thanh toán rõ ràng, xác thực qua email.", history: "Theo dõi những khoản học phí và kết quả thanh toán của bạn." };
    byId("breadcrumbCurrent").textContent = titles[view];
    byId("pageEyebrow").textContent = view === "tuition" ? "ĐỒNG HÀNH CÙNG VIỆC HỌC" : "KHÔNG GIAN CÁ NHÂN";
    byId("greeting").textContent = view === "overview" ? `Xin chào, ${currentUser?.full_name || "bạn"}` : titles[view];
    byId("pageSubtitle").textContent = subtitles[view];
    window.tuitionUI?.enter(view);
    if (focus) byId("mainContent").focus({ preventScroll: true });
}
function formatMoney(value) {
    // Giữ chuỗi Decimal từ API, không ép sang số thực.
    const [integer, fraction = "00"] = String(value).split(".");
    return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${fraction.padEnd(2, "0")} ₫`;
}
function renderBalance() {
    byId("balance").textContent = currentAccount ? (balanceHidden ? "••••••••" : formatMoney(currentAccount.balance)) : "—";
    const label = balanceHidden ? "Hiện số dư" : "Ẩn số dư";
    byId("balanceToggle").setAttribute("aria-label", label);
    byId("balanceToggle").setAttribute("aria-pressed", String(balanceHidden));
    byId("privacyButton").setAttribute("aria-pressed", String(balanceHidden));
    byId("privacyLabel").textContent = label;
    window.tuitionUI?.updatePayer();
}
function toggleBalance() { balanceHidden = !balanceHidden; renderBalance(); }
function clearSession() {
    accountLoadVersion += 1;
    window.tuitionUI?.reset();
    accessToken = null;
    currentUser = null;
    currentAccount = null;
    window.accountForms?.reset();
    balanceHidden = false;
    currentView = "overview";
    byId("accountSection").hidden = true;
    byId("loginSection").hidden = false;
    byId("password").value = "";
    byId("password").type = "password";
    byId("passwordToggle").setAttribute("aria-label", "Hiện mật khẩu");
    byId("passwordToggle").setAttribute("aria-pressed", "false");
    ["greeting", "accountNumber", "accountStatus", "fullName", "userName", "email", "phone", "identityNumber", "updatedAt", "headerName", "avatar", "summaryAvatar", "summaryName", "summaryEmail"].forEach(id => { byId(id).textContent = ""; });
    renderBalance();
}
async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
        const { allowStatuses = [], ...fetchOptions } = options;
        const response = await fetch(path, { ...fetchOptions, signal: controller.signal, cache: "no-store" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok && !allowStatuses.includes(response.status)) {
            const detail = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map(item => `${item.loc?.slice(1).join(".") || "Thông tin"}: ${item.msg}`).join("; ") : `Yêu cầu thất bại (HTTP ${response.status})`;
            const error = new Error(detail);
            error.status = response.status;
            error.data = data;
            throw error;
        }
        return data;
    } catch (error) {
        if (error.name === "AbortError") throw new Error("Máy chủ phản hồi quá lâu. Vui lòng thử lại.");
        if (error instanceof TypeError) throw new Error("Không kết nối được máy chủ. Vui lòng kiểm tra kết nối và thử lại.");
        throw error;
    } finally { clearTimeout(timeout); }
}
function renderUser(user) {
    currentUser = user;
    window.accountForms?.syncProfile();
    byId("fullName").textContent = user.full_name;
    byId("userName").textContent = user.username;
    byId("email").textContent = user.email || "Chưa cập nhật";
    byId("phone").textContent = user.phone || "Chưa cập nhật";
    byId("identityNumber").textContent = user.identity_number || "Chưa cập nhật";
    byId("headerName").textContent = user.full_name;
    byId("summaryName").textContent = user.full_name;
    byId("summaryEmail").textContent = user.email || "Chưa cập nhật";
    byId("avatar").textContent = initials(user.full_name);
    byId("summaryAvatar").textContent = initials(user.full_name);
}
async function loadAccount({ quiet = false } = {}) {
    const tokenUsed = accessToken;
    const version = ++accountLoadVersion;
    const headers = { Authorization: `Bearer ${tokenUsed}` };
    try {
        const [user, account] = await Promise.all([request("/users/me", { headers }), request("/accounts/me", { headers })]);
        // Không cập nhật giao diện từ phản hồi của phiên đã kết thúc.
        if (accessToken !== tokenUsed || !tokenUsed || version !== accountLoadVersion) return false;
        currentAccount = account;
        renderUser(user);
        byId("accountNumber").textContent = account.account_number;
        const active = account.status === "ACTIVE";
        byId("accountStatus").textContent = active ? "Đang hoạt động" : account.status === "LOCKED" ? "Đang khóa" : "Chưa xác định";
        byId("accountStatus").classList.toggle("locked", !active);
        renderBalance();
        byId("updatedAt").textContent = "Cập nhật lúc " + new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        byId("loginSection").hidden = true;
        byId("accountSection").hidden = false;
        if (!quiet) switchView(currentView, false);
        return true;
    } catch (error) {
        if (accessToken !== tokenUsed || version !== accountLoadVersion) return false;
        if (error.status === 401 || error.status === 403) {
            clearSession();
            byId("username").focus();
            if (error.status === 401) error.message = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
        }
        throw error;
    }
}
async function refreshLiveData() {
    if (liveRefreshing || !accessToken || !currentAccount || document.hidden || currentView === "profile" || window.tuitionUI?.isBusy()) return;
    liveRefreshing = true;
    try {
        if (await loadAccount({ quiet: true })) await window.tuitionUI?.refreshLive();
    } catch { /* Keep the current draft; explicit actions surface connection errors. */ }
    finally { liveRefreshing = false; }
}
setInterval(refreshLiveData, 5000);
window.addEventListener("focus", refreshLiveData);
window.addEventListener("online", refreshLiveData);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshLiveData(); });
byId("loginForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = byId("loginButton");
    if (button.disabled) return;
    const label = button.querySelector("span");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    label.textContent = "Đang đăng nhập…";
    showMessage("");
    try {
        const data = await request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: byId("username").value.trim(), password: byId("password").value }) });
        if (typeof data.access_token !== "string" || !data.access_token) throw new Error("Phản hồi đăng nhập không hợp lệ. Vui lòng thử lại.");
        accessToken = data.access_token;
        byId("password").value = "";
        if (await loadAccount()) {
            byId("mainContent").focus({ preventScroll: true });
            window.scrollTo(0, 0);
            showMessage("Chào mừng bạn trở lại iBanking.");
        }
    } catch (error) { clearSession(); showMessage(error.message, true); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); label.textContent = "Đăng nhập"; }
});
byId("refreshButton").addEventListener("click", async () => {
    const button = byId("refreshButton");
    const label = button.querySelector("span");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    label.textContent = "Đang cập nhật…";
    byId("updatedAt").textContent = "Đang lấy dữ liệu mới…";
    showMessage("");
    try { if (await loadAccount()) showMessage("Đã cập nhật thông tin mới nhất."); }
    catch (error) {
        if (accessToken) byId("updatedAt").textContent = "Cập nhật thất bại · Đang hiển thị dữ liệu trước đó";
        showMessage(error.message, true);
    } finally { button.disabled = false; button.removeAttribute("aria-busy"); label.textContent = "Làm mới dữ liệu"; }
});
byId("logoutButton").addEventListener("click", () => {
    window.tuitionUI?.forget();
    clearSession();
    byId("username").focus();
    showMessage("Đã đăng xuất trên trình duyệt này.");
});
byId("passwordToggle").addEventListener("click", () => {
    const show = byId("password").type === "password";
    byId("password").type = show ? "text" : "password";
    byId("passwordToggle").setAttribute("aria-label", show ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    byId("passwordToggle").setAttribute("aria-pressed", String(show));
});
async function copyAccount() {
    if (!currentAccount) return;
    const tokenUsed = accessToken;
    try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(String(currentAccount.account_number));
        if (tokenUsed === accessToken) showMessage("Đã sao chép số tài khoản.");
    } catch {
        if (tokenUsed === accessToken) showMessage("Trình duyệt chưa cho phép sao chép. Bạn có thể chọn số tài khoản để sao chép thủ công.", true);
    }
}
byId("copyAccountButton").addEventListener("click", copyAccount);
byId("quickCopy").addEventListener("click", copyAccount);
byId("balanceToggle").addEventListener("click", toggleBalance);
byId("privacyButton").addEventListener("click", toggleBalance);
byId("overviewNav").addEventListener("click", () => switchView("overview"));
["profileNav", "quickProfile", "detailsButton"].forEach(id => byId(id).addEventListener("click", () => switchView("profile")));
window.addEventListener("pageshow", event => { if (event.persisted) clearSession(); });
