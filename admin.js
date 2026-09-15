const adminState = {
  token: sessionStorage.getItem("nxt_admin_token") || "",
  submissions: [],
};

const adminElements = {
  login: document.querySelector("#admin-login"),
  loginForm: document.querySelector("#admin-login-form"),
  password: document.querySelector("#admin-password"),
  loginError: document.querySelector("#login-error"),
  dashboard: document.querySelector("#admin-dashboard"),
  logout: document.querySelector("#admin-logout"),
  count: document.querySelector("#submission-count"),
  plural: document.querySelector("#submission-plural"),
  search: document.querySelector("#submission-search"),
  loading: document.querySelector("#admin-loading"),
  list: document.querySelector("#submission-list"),
  empty: document.querySelector("#admin-empty"),
};

adminElements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = adminElements.loginForm.querySelector("button");
  const password = adminElements.password.value;
  adminElements.loginError.textContent = "";

  if (!password) {
    adminElements.loginError.textContent = "Entre le mot de passe administrateur.";
    return;
  }

  setAdminButtonLoading(button, true, "Connexion…", "Se connecter");
  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "Connexion impossible.");

    adminState.token = data.adminToken;
    sessionStorage.setItem("nxt_admin_token", data.adminToken);
    await showDashboard();
  } catch (error) {
    adminElements.loginError.textContent = error.message === "Failed to fetch"
      ? "Le serveur ne répond pas."
      : error.message;
    adminElements.password.select();
  } finally {
    setAdminButtonLoading(button, false, "Connexion…", "Se connecter");
  }
});

adminElements.logout.addEventListener("click", () => {
  sessionStorage.removeItem("nxt_admin_token");
  adminState.token = "";
  adminState.submissions = [];
  adminElements.dashboard.hidden = true;
  adminElements.login.hidden = false;
  adminElements.loginForm.reset();
  adminElements.password.focus();
});

adminElements.search.addEventListener("input", () => renderSubmissions(adminElements.search.value));

async function showDashboard() {
  adminElements.login.hidden = true;
  adminElements.dashboard.hidden = false;
  adminElements.loading.hidden = false;
  adminElements.empty.hidden = true;

  try {
    const response = await fetch("/api/admin/responses", {
      headers: { Authorization: `Bearer ${adminState.token}` },
      cache: "no-store",
    });
    if (response.status === 401) {
      sessionStorage.removeItem("nxt_admin_token");
      adminState.token = "";
      adminElements.dashboard.hidden = true;
      adminElements.login.hidden = false;
      adminElements.loginError.textContent = "Ta session a expiré. Reconnecte-toi.";
      return;
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "Impossible de charger les réponses.");

    adminState.submissions = Array.isArray(data.submissions) ? data.submissions : [];
    renderSubmissions();
  } catch (error) {
    adminElements.loading.textContent = error.message === "Failed to fetch" ? "Le serveur ne répond pas." : error.message;
    return;
  }
  adminElements.loading.hidden = true;
}

function renderSubmissions(query = "") {
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = adminState.submissions.filter((submission) => {
    const searchable = `${submission.id || ""} ${submission.accessCode || ""}`.toLowerCase();
    return searchable.includes(normalizedQuery);
  });

  adminElements.count.textContent = filtered.length;
  adminElements.plural.hidden = filtered.length === 1;
  adminElements.list.replaceChildren();
  adminElements.empty.hidden = filtered.length !== 0;

  filtered.forEach((submission) => adminElements.list.appendChild(createSubmission(submission)));
}

function createSubmission(submission) {
  const details = document.createElement("details");
  details.className = "submission";
  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="submission__identity">
      <small>ID</small>
      <strong>${escapeAdminHtml(submission.id || "Sans identifiant")}</strong>
    </span>
    <span class="submission__code">
      <small>Code</small>
      <strong>${escapeAdminHtml(submission.accessCode || "—")}</strong>
    </span>
    <time datetime="${escapeAdminHtml(submission.submittedAt || "")}">${formatAdminDate(submission.submittedAt)}</time>
    <span class="submission__chevron" aria-hidden="true">⌄</span>
  `;
  details.appendChild(summary);

  const answersContainer = document.createElement("div");
  answersContainer.className = "submission__answers";
  const titles = new Map((submission.questions || []).map((question) => [question.id, question.title]));
  Object.entries(submission.answers || {}).forEach(([questionId, answer], index) => {
    const answerElement = document.createElement("article");
    answerElement.className = "admin-answer";
    const questionTitle = titles.get(questionId) || questionId;
    answerElement.innerHTML = `
      <span>${String(index + 1).padStart(2, "0")}</span>
      <div><h3>${escapeAdminHtml(questionTitle)}</h3><p>${escapeAdminHtml(String(answer))}</p></div>
    `;
    answersContainer.appendChild(answerElement);
  });
  details.appendChild(answersContainer);
  return details;
}

function formatAdminDate(value) {
  if (!value) return "Date inconnue";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date inconnue";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  }).format(date);
}

function escapeAdminHtml(value) {
  const element = document.createElement("span");
  element.textContent = value;
  return element.innerHTML;
}

function setAdminButtonLoading(button, loading, loadingLabel, normalLabel) {
  button.disabled = loading;
  button.querySelector("span:first-child").textContent = loading ? loadingLabel : normalLabel;
}

if (adminState.token) showDashboard();
