

const API_BASE = "";

/* ── Theme (applied IMMEDIATELY, before DOMContentLoaded) ──────────────────── */
const Theme = {
  apply() {
    const user = Auth.getUser();
    const dark =
      user?.dark_mode === true || localStorage.getItem("cq_dark") === "true";
    document.documentElement.setAttribute(
      "data-theme",
      dark ? "dark" : "light",
    );
    const lang =
      user?.display_language || localStorage.getItem("cq_lang") || "English";
    const langCode = {
      English: "en",
      Hindi: "hi",
      Spanish: "es",
      French: "fr",
      German: "de",
      Japanese: "ja",
    };
    document.documentElement.setAttribute("lang", langCode[lang] || "en");
  },
  setDark(val) {
    localStorage.setItem("cq_dark", String(val));
    document.documentElement.setAttribute("data-theme", val ? "dark" : "light");
  },
  setLang(lang) {
    localStorage.setItem("cq_lang", lang);
    const langCode = {
      English: "en",
      Hindi: "hi",
      Spanish: "es",
      French: "fr",
      German: "de",
      Japanese: "ja",
    };
    document.documentElement.setAttribute("lang", langCode[lang] || "en");
  },
};

/* ── Auth helpers ───────────────────────────────────────────────────────────── */
const Auth = {
  getToken() {
    return localStorage.getItem("cq_token");
  },
  getUser() {
    const u = localStorage.getItem("cq_user");
    return u ? JSON.parse(u) : null;
  },
  setSession(token, user) {
    localStorage.setItem("cq_token", token);
    localStorage.setItem("cq_user", JSON.stringify(user));
    if (user?.dark_mode !== undefined)
      localStorage.setItem("cq_dark", String(user.dark_mode));
    if (user?.display_language)
      localStorage.setItem("cq_lang", user.display_language);
    Theme.apply();
  },
  clearSession() {
    localStorage.removeItem("cq_token");
    localStorage.removeItem("cq_user");
  },
  isLoggedIn() {
    return !!this.getToken();
  },
  requireAuth() {
    if (!this.isLoggedIn()) {
      window.location.href = "index.html";
      return false;
    }
    return true;
  },
  redirectIfLoggedIn() {
    if (this.isLoggedIn()) window.location.href = "dashboard.html";
  },
};

// // Run before anything else so there's no flash of light mode
// Theme.apply();

document.addEventListener("DOMContentLoaded", () => {
  Theme.apply();
});

/* ── Core fetch ─────────────────────────────────────────────────────────────── */
async function apiFetch(path, options = {}) {
  const token = Auth.getToken();
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(API_BASE + path, { ...options, headers });
  } catch (e) {
    throw new Error("Network error — is the server running?");
  }
  if (res.status === 401) {
    Auth.clearSession();
    window.location.href = "index.html";
    return;
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = Array.isArray(data.detail)
      ? data.detail.map((e) => e.msg).join(", ")
      : data.detail || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

/* ── Auth API ───────────────────────────────────────────────────────────────── */
const AuthAPI = {
  async login(email, password) {
    // const fd = new URLSearchParams();
    // fd.append("username", email);
    // fd.append("password", password);
    // const res = await fetch("/api/auth/login", {
    //   method: "POST",
    //   headers: { "Content-Type": "application/x-www-form-urlencoded" },
    //   body: fd,
    // });

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: email,
        password: password,
      }),
    });
    const data = await res.json();
    console.log("LOGIN RESPONSE:", data);
    if (!res.ok) throw new Error(data.detail || "Login failed");
    Auth.setSession(data.access_token, data.user);
    return data;
  },
  async signup(fullName, email, password) {
    const data = await apiFetch("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ full_name: fullName, email, password }),
    });
    Auth.setSession(data.access_token, data.user);
    return data;
  },
  logout() {
    Auth.clearSession();
    window.location.href = "index.html";
  },
  getMe() {
    return apiFetch("/api/auth/me");
  },
};

/* ── Forgot Password API ────────────────────────────────────────────────────── */
const ForgotPasswordAPI = {
  /** Step 1: send OTP to the registered email. No token needed. */
  sendOtp(email) {
    return apiFetch("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },
  /** Step 2: verify OTP + set new password. No token needed. */
  resetPassword(email, otp, newPassword, confirmPassword) {
    return apiFetch("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        email,
        otp,
        new_password: newPassword,
        confirm_password: confirmPassword,
      }),
    });
  },
};

/* ── Dashboard API ──────────────────────────────────────────────────────────── */
const DashboardAPI = {
  getStats() {
    return apiFetch("/api/dashboard/stats");
  },
  getUpcomingQuizzes(limit = 6) {
    return apiFetch(`/api/dashboard/upcoming-quizzes?limit=${limit}`);
  },
  getActiveQuizzes() {
    return apiFetch("/api/dashboard/active-quizzes");
  },
};

/* ── Quiz API ───────────────────────────────────────────────────────────────── */
const QuizAPI = {
  list(search = "", status = "") {
    const p = new URLSearchParams();
    if (search) p.set("search", search);
    if (status) p.set("status", status);
    return apiFetch(`/api/quizzes?${p}`);
  },
  get(id) {
    return apiFetch(`/api/quizzes/${id}`);
  },
  create(payload) {
    return apiFetch("/api/quizzes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  update(id, p) {
    return apiFetch(`/api/quizzes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(p),
    });
  },
  delete(id) {
    return apiFetch(`/api/quizzes/${id}`, { method: "DELETE" });
  },
  take(id) {
    return apiFetch(`/api/quizzes/${id}/take`);
  },
  submit(id, answers) {
    return apiFetch(`/api/quizzes/${id}/submit`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    });
  },
};

/* ── Analytics API ──────────────────────────────────────────────────────────── */
const AnalyticsAPI = {
  get() {
    return apiFetch("/api/analytics");
  },
};

/* ── Leaderboard API ────────────────────────────────────────────────────────── */
const LeaderboardAPI = {
  get(quizId) {
    return apiFetch(`/api/leaderboard/${quizId}`);
  },
};

/* ── Settings API ───────────────────────────────────────────────────────────── */
const SettingsAPI = {
  getProfile() {
    return apiFetch("/api/settings/profile");
  },
  updateProfile(payload) {
    return apiFetch("/api/settings/profile", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  requestOtp() {
    return apiFetch("/api/settings/security/request-otp", { method: "POST" });
  },
  resetPasswordWithOtp(otp, newPw, confirmPw) {
    return apiFetch("/api/settings/security/verify-otp", {
      method: "POST",
      body: JSON.stringify({
        otp,
        new_password: newPw,
        confirm_password: confirmPw,
      }),
    });
  },
  changePassword(cur, nw, cnw) {
    return apiFetch("/api/settings/security/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: cur,
        new_password: nw,
        confirm_password: cnw,
      }),
    });
  },
  updateNotificationPrefs(emailDigests, pushAlerts) {
    return apiFetch("/api/settings/notifications", {
      method: "PATCH",
      body: JSON.stringify({
        email_digests: emailDigests,
        push_alerts: pushAlerts,
      }),
    });
  },
};

/* ── Notifications API ──────────────────────────────────────────────────────── */
const NotificationsAPI = {
  list(unreadOnly = false) {
    return apiFetch(`/api/notifications?unread_only=${unreadOnly}`);
  },
  markRead(id) {
    return apiFetch(`/api/notifications/${id}/read`, { method: "PATCH" });
  },
  markAllRead() {
    return apiFetch("/api/notifications/mark-all-read", { method: "POST" });
  },
  delete(id) {
    return apiFetch(`/api/notifications/${id}`, { method: "DELETE" });
  },
};

/* ── UI helpers ─────────────────────────────────────────────────────────────── */
const UI = {
  toast(message, type = "success") {
    document.querySelectorAll(".cq-toast").forEach((t) => t.remove());
    const t = document.createElement("div");
    t.className = "cq-toast";
    t.innerHTML = `<i class="ri-${type === "success" ? "checkbox-circle" : "error-warning"}-line"></i><span>${message}</span>`;
    t.style.cssText = `position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;align-items:center;gap:10px;
      background:${type === "success" ? "#2ED573" : "#FF4757"};color:#fff;padding:14px 20px;border-radius:10px;
      font-size:14px;font-weight:500;font-family:Inter,sans-serif;box-shadow:0 4px 20px rgba(0,0,0,.15);animation:cqSlideIn .3s ease;`;
    if (!document.getElementById("cq-anim")) {
      const s = document.createElement("style");
      s.id = "cq-anim";
      s.textContent = `@keyframes cqSlideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}
        @keyframes cqSlideOut{from{transform:translateX(0);opacity:1}to{transform:translateX(120%);opacity:0}}
        @keyframes cqSpin{to{transform:rotate(360deg)}}`;
      document.head.appendChild(s);
    }
    document.body.appendChild(t);
    setTimeout(() => {
      t.style.animation = "cqSlideOut .3s ease forwards";
      setTimeout(() => t.remove(), 300);
    }, 3500);
  },

  setLoading(btn, loading) {
    if (loading) {
      btn.dataset.orig = btn.innerHTML;
      btn.innerHTML =
        '<i class="ri-loader-4-line" style="animation:cqSpin .8s linear infinite;display:inline-block;margin-right:6px;"></i>Loading...';
      btn.disabled = true;
    } else {
      btn.innerHTML = btn.dataset.orig || btn.innerHTML;
      btn.disabled = false;
    }
  },

  populateSidebar() {
    const user = Auth.getUser();
    if (!user) return;
    document
      .querySelectorAll(".user-name")
      .forEach(
        (el) => (el.textContent = `Welcome, ${user.full_name.split(" ")[0]}!`),
      );
    document.querySelectorAll(".user-avatar").forEach((el) => {
      if (user.profile_picture) {
        el.style.cssText = "overflow:hidden;padding:0;";
        el.innerHTML = `<img src="${user.profile_picture}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
      } else {
        const ini = user.full_name
          .split(" ")
          .map((n) => n[0])
          .join("")
          .toUpperCase()
          .slice(0, 2);
        el.textContent = ini;
        el.style.cssText = "";
      }
    });
  },

  async updateNotifBadge() {
    try {
      const data = await NotificationsAPI.list();
      const count = data.unread_count || 0;
      document.querySelectorAll(".notification-btn .badge").forEach((b) => {
        b.textContent = count;
        b.style.display = count > 0 ? "flex" : "none";
      });
    } catch (_) {}
  },

  formatDate(d) {
    return d
      ? new Date(d).toLocaleDateString("en-IN", {
          year: "numeric",
          month: "short",
          day: "numeric",
        })
      : "—";
  },

  formatTime(t) {
    if (!t) return "";
    const [h, m] = t.split(":");
    const d = new Date();
    d.setHours(+h, +m);
    return d.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  },

  /** Build quiz card — completed shows Leaderboard button */
  buildQuizCard(quiz) {
    const colors = ["#61DBFB", "#FFB347", "#CBAACB"];
    const avatars = colors
      .map(
        (c, i) =>
          `<div class="avatar-placeholder" style="background:${c};color:#fff;width:24px;height:24px;border-radius:50%;
       border:2px solid #fff;margin-left:${i === 0 ? "0" : "-8px"};display:flex;align-items:center;
       justify-content:center;font-size:10px;font-weight:600;">${i + 1}</div>`,
      )
      .join("");
    const timeStr = quiz.scheduled_time
      ? UI.formatTime(quiz.scheduled_time)
      : "";
    const bc =
      quiz.status === "active"
        ? "#e6fff1"
        : quiz.status === "completed"
          ? "#f1f2f6"
          : "#eef2ff";
    const tc =
      quiz.status === "active"
        ? "#2ED573"
        : quiz.status === "completed"
          ? "#747d8c"
          : "var(--primary-color)";

    let footerBtn;
    if (quiz.is_attempted || quiz.status === "completed") {
      footerBtn = `<div style="display:flex;gap:8px;align-items:center;">
        <button style="padding:5px 12px;font-size:12px;border:1px solid #ccc;color:#999;
                       background:transparent;border-radius:20px;cursor:default;" disabled>✅ Done</button>
        <a href="leaderboard.html?id=${quiz.id}"
           style="padding:5px 12px;font-size:12px;border:1px solid var(--primary-color);
                  color:var(--primary-color);border-radius:20px;background:transparent;
                  text-decoration:none;display:inline-flex;align-items:center;gap:4px;">
          <i class="ri-trophy-line"></i> Board
        </a>
      </div>`;
    } else if (quiz.status === "upcoming") {
      footerBtn = `<button style="padding:6px 12px;font-size:13px;opacity:.5;cursor:not-allowed;
        border:1px solid var(--border-color);border-radius:20px;background:transparent;" disabled>Not Started</button>`;
    } else {
      footerBtn = `<button onclick="window.location.href='take-quiz.html?id=${quiz.id}'"
        style="padding:6px 14px;font-size:13px;border:1px solid var(--primary-color);
               color:var(--primary-color);background:transparent;border-radius:20px;
               cursor:pointer;font-family:var(--font-family);font-weight:600;">Start Quiz</button>`;
    }

    return `
      <div class="card quiz-card" data-quiz-id="${quiz.id}">
        <div class="quiz-meta" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <span style="font-size:12px;font-weight:600;text-transform:uppercase;color:var(--text-light);letter-spacing:.5px;">
            ${(quiz.category || "").toUpperCase()}
          </span>
          <span style="background:${bc};color:${tc};padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;">
            ${quiz.status}
          </span>
        </div>
        <h3 style="font-size:16px;font-weight:700;margin-bottom:16px;line-height:1.4;">${quiz.title}</h3>
        <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:20px;">
          ${quiz.scheduled_date ? `<div style="display:flex;align-items:center;gap:8px;color:var(--text-light);font-size:13px;"><i class="ri-calendar-line"></i>${quiz.scheduled_date}</div>` : ""}
          ${timeStr ? `<div style="display:flex;align-items:center;gap:8px;color:var(--text-light);font-size:13px;"><i class="ri-time-line"></i>${timeStr} (${quiz.duration_mins} Mins)</div>` : ""}
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;padding-top:16px;border-top:1px dotted var(--border-color);">
          <div style="display:flex;align-items:center;">
            <div style="display:flex;">${avatars}</div>
            <span style="margin-left:8px;font-size:12px;color:var(--text-light);">+${quiz.enrolled_count || 0} enrolled</span>
          </div>
          ${footerBtn}
        </div>
      </div>`;
  },
};

/* ── Page bootstrap ─────────────────────────────────────────────────────────── */
function initProtectedPage() {
  if (!Auth.requireAuth()) return false;
  Theme.apply();
  UI.populateSidebar();
  document
    .querySelectorAll('.user-role a[href="index.html"]')
    .forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        AuthAPI.logout();
      });
    });
  document.querySelectorAll(".notification-btn").forEach((btn) => {
    btn.addEventListener(
      "click",
      () => (window.location.href = "notifications.html"),
    );
  });
  UI.updateNotifBadge();
  return true;
}
