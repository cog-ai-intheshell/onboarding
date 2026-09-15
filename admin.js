const adminState = {
  token: sessionStorage.getItem("nxt_admin_token") || "",
  submissions: [],
  codes: [],
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
  codeForm: document.querySelector("#admin-code-form"),
  codeInput: document.querySelector("#new-access-code"),
  generateCode: document.querySelector("#generate-code"),
  codeFeedback: document.querySelector("#code-feedback"),
  codeList: document.querySelector("#admin-code-list"),
  codeCount: document.querySelector("#code-count"),
  codePlural: document.querySelector("#code-plural"),
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
  adminState.codes = [];
  adminElements.dashboard.hidden = true;
  adminElements.login.hidden = false;
  adminElements.loginForm.reset();
  adminElements.password.focus();
});

adminElements.search.addEventListener("input", () => renderSubmissions(adminElements.search.value));

adminElements.codeInput.addEventListener("input", () => {
  adminElements.codeInput.value = adminElements.codeInput.value.replace(/[^a-z]/gi, "").toUpperCase().slice(0, 6);
  setCodeFeedback("Entre jusqu’à 6 lettres, ou génère un code aléatoire.");
});

adminElements.codeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await createCode(false);
});

adminElements.generateCode.addEventListener("click", () => createCode(true));

async function showDashboard() {
  adminElements.login.hidden = true;
  adminElements.dashboard.hidden = false;
  adminElements.loading.hidden = false;
  adminElements.empty.hidden = true;

  try {
    await Promise.all([loadSubmissions(), loadCodes()]);
  } catch (error) {
    if (error.message === "SESSION_EXPIRED") return;
    adminElements.loading.textContent = error.message === "Failed to fetch" ? "Le serveur ne répond pas." : error.message;
    return;
  }
  adminElements.loading.hidden = true;
}

async function adminFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
      Authorization: `Bearer ${adminState.token}`,
    },
    cache: "no-store",
  });
  const data = await response.json();
  if (response.status === 401) {
    expireAdminSession();
    throw new Error("SESSION_EXPIRED");
  }
  if (!response.ok) throw new Error(data.message || "La demande a échoué.");
  return data;
}

function expireAdminSession() {
  sessionStorage.removeItem("nxt_admin_token");
  adminState.token = "";
  adminElements.dashboard.hidden = true;
  adminElements.login.hidden = false;
  adminElements.loginError.textContent = "Ta session a expiré. Reconnecte-toi.";
}

async function loadSubmissions() {
  const data = await adminFetch("/api/admin/responses");
  adminState.submissions = Array.isArray(data.submissions) ? data.submissions : [];
  renderSubmissions();
}

async function loadCodes() {
  const data = await adminFetch("/api/admin/codes");
  adminState.codes = Array.isArray(data.codes) ? data.codes : [];
  renderCodes();
}

async function createCode(generate) {
  const code = adminElements.codeInput.value.trim().toUpperCase();
  if (!generate && !/^[A-Z]{1,6}$/.test(code)) {
    setCodeFeedback("Le code doit contenir entre 1 et 6 lettres.", true);
    adminElements.codeInput.focus();
    return;
  }

  const button = generate ? adminElements.generateCode : adminElements.codeForm.querySelector('button[type="submit"]');
  button.disabled = true;
  setCodeFeedback(generate ? "Génération du code…" : "Création du code…");
  try {
    const data = await adminFetch("/api/admin/codes", {
      method: "POST",
      body: JSON.stringify(generate ? { generate: true } : { code }),
    });
    adminElements.codeInput.value = "";
    await loadCodes();
    setCodeFeedback(`Le code ${data.code} est actif et peut être utilisé immédiatement.`, false, true);
  } catch (error) {
    if (error.message !== "SESSION_EXPIRED") {
      setCodeFeedback(error.message === "Failed to fetch" ? "Le serveur ne répond pas." : error.message, true);
    }
  } finally {
    button.disabled = false;
  }
}

function renderCodes() {
  adminElements.codeCount.textContent = adminState.codes.length;
  adminElements.codePlural.hidden = adminState.codes.length === 1;
  adminElements.codeList.replaceChildren();

  adminState.codes.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "admin-code-row";

    const identity = document.createElement("div");
    identity.className = "admin-code-row__identity";
    const code = document.createElement("strong");
    code.textContent = entry.code;
    const state = document.createElement("span");
    state.className = entry.active ? "is-active" : "is-inactive";
    state.textContent = entry.active ? "Actif" : "Inactif";
    identity.append(code, state);

    const metadata = document.createElement("small");
    const count = Number(entry.submissionCount) || 0;
    metadata.textContent = `${count} réponse${count === 1 ? "" : "s"} · créé ${formatAdminDate(entry.createdAt)}`;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "admin-code-toggle";
    toggle.textContent = entry.active ? "Désactiver" : "Réactiver";
    toggle.addEventListener("click", () => toggleCode(entry, toggle));

    row.append(identity, metadata, toggle);
    adminElements.codeList.appendChild(row);
  });
}

async function toggleCode(entry, button) {
  button.disabled = true;
  try {
    await adminFetch("/api/admin/codes", {
      method: "PATCH",
      body: JSON.stringify({ code: entry.code, active: !entry.active }),
    });
    entry.active = !entry.active;
    renderCodes();
    setCodeFeedback(`Le code ${entry.code} est maintenant ${entry.active ? "actif" : "inactif"}.`, false, true);
  } catch (error) {
    if (error.message !== "SESSION_EXPIRED") setCodeFeedback(error.message, true);
    button.disabled = false;
  }
}

function setCodeFeedback(message, error = false, success = false) {
  adminElements.codeFeedback.textContent = message;
  adminElements.codeFeedback.classList.toggle("is-error", error);
  adminElements.codeFeedback.classList.toggle("is-success", success);
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
