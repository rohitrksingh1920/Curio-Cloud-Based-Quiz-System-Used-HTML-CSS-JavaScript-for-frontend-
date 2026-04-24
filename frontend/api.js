



const API_BASE = "/api";

/* ── Theme ──────────────────────────────────────────────────────────────────── */
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

/* ── Auth helpers ────────────────────────────────────────────────────────────── */
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

document.addEventListener("DOMContentLoaded", () => Theme.apply());

/* ── Core fetch ──────────────────────────────────────────────────────────────── */
async function apiFetch(path, options = {}) {
  const token = Auth.getToken();
  const headers = { ...options.headers };

  // Only set Content-Type for JSON — let browser set it for FormData
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new Error("Network error — is the server running?");
  }

  // Token expired or invalid → clear session and redirect to login
  if (res.status === 401) {
    Auth.clearSession();
    // Avoid redirect loop if already on login page
    if (!window.location.pathname.includes("index.html")) {
      window.location.href = "index.html";
    }
    return;
  }

  // No content
  if (res.status === 204) return null;

  let data = {};
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }

  if (!res.ok) {
    // FastAPI validation errors come as detail array
    let msg;
    if (Array.isArray(data.detail)) {
      msg = data.detail
        .map((e) => e.msg || e.message || JSON.stringify(e))
        .join(", ");
    } else {
      msg = data.detail || data.message || `HTTP ${res.status}`;
    }

    // FIX: use || so the real backend message is shown when present.
    // Previously, 500 unconditionally overwrote the detail with a generic
    // message — hiding SMTP errors, validation errors, and all real causes.
    if (res.status === 403) msg = msg || "Access denied. You do not have permission.";
    if (res.status === 404) msg = msg || "Resource not found.";
    if (res.status === 409) msg = msg || "Conflict — this resource already exists.";
    if (res.status === 413) msg = msg || "File too large.";
    if (res.status === 422) msg = msg || "Validation error. Please check your input.";
    if (res.status === 500) msg = msg || "Server error. Please try again later.";
    if (res.status === 503) msg = msg || "Service unavailable. Please try again later.";

    throw new Error(msg);
  }

  return data;
}

/* ── Auth API ────────────────────────────────────────────────────────────────── */
const AuthAPI = {
  async login(email, password) {
    // Login uses raw fetch so we can handle errors before calling setSession
    let res,
      data = {};
    try {
      res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ email, password }),
      });
      try {
        data = await res.json();
      } catch {
        /* empty */
      }
    } catch {
      throw new Error("Network error — is the server running?");
    }

    if (!res.ok) {
      const msg = Array.isArray(data.detail)
        ? data.detail.map((e) => e.msg || e.message).join(", ")
        : data.detail || data.message || "Invalid email or password.";
      throw new Error(msg);
    }

    Auth.setSession(data.access_token, data.user);
    return data;
  },

  async signup(fullName, email, password) {
    const data = await apiFetch("/auth/signup", {
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
    return apiFetch("/auth/me");
  },
};

/* ── Dashboard API ───────────────────────────────────────────────────────────── */
const DashboardAPI = {
  getStats() {
    return apiFetch("/dashboard/stats");
  },
  getUpcomingQuizzes(limit = 6) {
    return apiFetch(`/dashboard/upcoming-quizzes?limit=${limit}`);
  },
  getActiveQuizzes() {
    return apiFetch("/dashboard/active-quizzes");
  },
};

/* ── Quiz API ─────────────────────────────────────────────────────────────────── */
const QuizAPI = {
  list(search = "", status = "") {
    const p = new URLSearchParams();
    if (search) p.set("search", search);
    if (status) p.set("status", status);
    return apiFetch(`/quizzes?${p}`);
  },
  get(id) {
    return apiFetch(`/quizzes/${id}`);
  },
  create(payload) {
    return apiFetch("/quizzes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  update(id, p) {
    return apiFetch(`/quizzes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(p),
    });
  },
  delete(id) {
    return apiFetch(`/quizzes/${id}`, { method: "DELETE" });
  },
  take(id) {
    return apiFetch(`/quizzes/${id}/take`);
  },
  submit(id, answers) {
    return apiFetch(`/quizzes/${id}/submit`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    });
  },
};

/* ── Analytics API ───────────────────────────────────────────────────────────── */
const AnalyticsAPI = {
  get() {
    return apiFetch("/analytics");
  },
};

/* ── Leaderboard API ─────────────────────────────────────────────────────────── */
const LeaderboardAPI = {
  get(quizId) {
    return apiFetch(`/leaderboard/${quizId}`);
  },
};

/* ── Settings API ────────────────────────────────────────────────────────────── */
const SettingsAPI = {
  getProfile() {
    return apiFetch("/settings/profile");
  },
  updateProfile(payload) {
    return apiFetch("/settings/profile", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  requestOtp() {
    return apiFetch("/settings/security/request-otp", { method: "POST" });
  },
  resetPasswordWithOtp(otp, newPw, confirmPw) {
    return apiFetch("/settings/security/verify-otp", {
      method: "POST",
      body: JSON.stringify({
        otp,
        new_password: newPw,
        confirm_password: confirmPw,
      }),
    });
  },
  changePassword(cur, nw, cnw) {
    return apiFetch("/settings/security/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: cur,
        new_password: nw,
        confirm_password: cnw,
      }),
    });
  },
  updateNotificationPrefs(emailDigests, pushAlerts) {
    return apiFetch("/settings/notifications", {
      method: "PATCH",
      body: JSON.stringify({
        email_digests: emailDigests,
        push_alerts: pushAlerts,
      }),
    });
  },
  uploadAvatar(formData) {
    // Let browser set multipart boundary — do NOT set Content-Type manually
    return apiFetch("/settings/profile/avatar", {
      method: "POST",
      body: formData,
    });
  },
};

/* ── Notifications API ───────────────────────────────────────────────────────── */
const NotificationsAPI = {
  list(unreadOnly = false) {
    return apiFetch(`/notifications?unread_only=${unreadOnly}`);
  },
  markRead(id) {
    return apiFetch(`/notifications/${id}/read`, { method: "PATCH" });
  },
  markAllRead() {
    return apiFetch("/notifications/mark-all-read", { method: "POST" });
  },
  delete(id) {
    return apiFetch(`/notifications/${id}`, { method: "DELETE" });
  },
};

/* ── Forgot Password API ─────────────────────────────────────────────────────── */
const ForgotPasswordAPI = {
  sendOtp(email) {
    return apiFetch("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },
  resetPassword(email, otp, newPassword, confirmPassword) {
    return apiFetch("/auth/reset-password", {
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

/* ── Admin API ───────────────────────────────────────────────────────────────── */
const AdminAPI = {
  listUsers(role) {
    return apiFetch(`/admin/users${role ? "?role=" + role : ""}`);
  },
  listStudents() {
    return apiFetch("/admin/users/students");
  },
  updateRole(id, role) {
    return apiFetch(`/admin/users/${id}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
  },
  toggleActive(id) {
    return apiFetch(`/admin/users/${id}/activate`, { method: "PATCH" });
  },
  deleteUser(id) {
    return apiFetch(`/admin/users/${id}`, { method: "DELETE" });
  },
};

/* ── Enrollment API ──────────────────────────────────────────────────────────── */
const EnrollAPI = {
  enroll(quizId, userIds) {
    return apiFetch(`/quizzes/${quizId}/enroll`, {
      method: "POST",
      body: JSON.stringify({ user_ids: userIds }),
    });
  },
  removeEnrollment(quizId, uid) {
    return apiFetch(`/quizzes/${quizId}/enroll/${uid}`, { method: "DELETE" });
  },
  getStudents(quizId) {
    return apiFetch(`/quizzes/${quizId}/students`);
  },
};

/* ── UI helpers ──────────────────────────────────────────────────────────────── */
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
    if (!btn) return;
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

  applyRBAC() {
    const user = Auth.getUser();
    if (!user) return;
    const isStudent = user.role === "student";
    const isAdmin = user.role === "admin";

    if (isStudent) {
      document
        .querySelectorAll(
          'a[href="create-quiz.html"], #create-quiz-btn, [data-rbac="teacher"]',
        )
        .forEach((el) => (el.style.display = "none"));
      document.querySelectorAll(".menu-item").forEach((el) => {
        if (el.href && el.href.includes("create-quiz.html"))
          el.style.display = "none";
      });
      document
        .querySelectorAll(".header-actions .btn-primary")
        .forEach((el) => {
          if (el.textContent.includes("Create")) el.style.display = "none";
        });
      document
        .querySelectorAll('[data-action="delete"]')
        .forEach((el) => (el.style.display = "none"));
      document.querySelectorAll(".page-header .btn-primary").forEach((el) => {
        if (el.textContent.includes("Create")) el.style.display = "none";
      });
    }

    if (!isAdmin) {
      document
        .querySelectorAll('[data-rbac="admin"]')
        .forEach((el) => (el.style.display = "none"));
    }
  },

  async updateNotifBadge() {
    try {
      const data = await NotificationsAPI.list();
      const count = data?.unread_count || 0;
      document.querySelectorAll(".notification-btn .badge").forEach((b) => {
        b.textContent = count;
        b.style.display = count > 0 ? "flex" : "none";
      });
    } catch {
      /* silent — badge is non-critical */
    }
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

  buildQuizCard(quiz) {
    const colors = ["#61DBFB", "#FFB347", "#CBAACB"];
    const avatars = colors
      .map(
        (
          c,
          i,
        ) => `<div class="avatar-placeholder" style="background:${c};color:#fff;width:24px;height:24px;
        border-radius:50%;border:2px solid #fff;margin-left:${i === 0 ? "0" : "-8px"};display:flex;
        align-items:center;justify-content:center;font-size:10px;font-weight:600;">${i + 1}</div>`,
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
        <button style="padding:5px 12px;font-size:12px;border:1px solid #ccc;color:#999;background:transparent;border-radius:20px;cursor:default;" disabled>✅ Done</button>
        <a href="leaderboard.html?id=${quiz.id}" style="padding:5px 12px;font-size:12px;border:1px solid var(--primary-color);color:var(--primary-color);border-radius:20px;background:transparent;text-decoration:none;display:inline-flex;align-items:center;gap:4px;">
          <i class="ri-trophy-line"></i> Board
        </a>
      </div>`;
    } else if (quiz.status === "upcoming") {
      footerBtn = `<button style="padding:6px 12px;font-size:13px;opacity:.5;cursor:not-allowed;border:1px solid var(--border-color);border-radius:20px;background:transparent;" disabled>Not Started</button>`;
    } else {
      footerBtn = `<button onclick="window.location.href='take-quiz.html?id=${quiz.id}'" style="padding:6px 14px;font-size:13px;border:1px solid var(--primary-color);color:var(--primary-color);background:transparent;border-radius:20px;cursor:pointer;font-family:var(--font-family);font-weight:600;">Start Quiz</button>`;
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

/* ── Page bootstrap ──────────────────────────────────────────────────────────── */
function initProtectedPage() {
  if (!Auth.requireAuth()) return false;
  Theme.apply();
  UI.populateSidebar();
  UI.applyRBAC();
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

