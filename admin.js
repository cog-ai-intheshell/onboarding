const adminState = {
  token: sessionStorage.getItem("nxt_admin_token") || "",
  submissions: [],
  codes: [],
  questions: [],
  questionsDirty: false,
  planningSlots: [],
  planningMonth: new Date(Date.UTC(2026, 9, 1)),
  planningDrag: null,
  planningJustDragged: false,
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
  questionList: document.querySelector("#admin-question-list"),
  questionCount: document.querySelector("#question-count"),
  questionPlural: document.querySelector("#question-plural"),
  addQuestion: document.querySelector("#add-question"),
  saveQuestions: document.querySelector("#save-questions"),
  questionFeedback: document.querySelector("#question-feedback"),
  planningCalendar: document.querySelector("#admin-planning-calendar"),
  planningMonth: document.querySelector("#admin-planning-month"),
  planningForm: document.querySelector("#admin-planning-form"),
  planningDate: document.querySelector("#admin-planning-date"),
  planningFeedback: document.querySelector("#admin-planning-feedback"),
  planningTotal: document.querySelector("#planning-total"),
  planningOpen: document.querySelector("#planning-open"),
  planningTaken: document.querySelector("#planning-taken"),
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
  adminState.questions = [];
  adminState.questionsDirty = false;
  adminState.planningSlots = [];
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
adminElements.addQuestion.addEventListener("click", addQuestion);
adminElements.saveQuestions.addEventListener("click", saveQuestions);
adminElements.planningForm.addEventListener("submit", createPlanningSlot);
document.querySelectorAll("[data-admin-month-shift]").forEach((button) => {
  button.addEventListener("click", () => {
    adminState.planningMonth = new Date(Date.UTC(
      adminState.planningMonth.getUTCFullYear(),
      adminState.planningMonth.getUTCMonth() + Number(button.dataset.adminMonthShift),
      1,
    ));
    renderAdminPlanning();
  });
});

window.addEventListener("beforeunload", (event) => {
  if (!adminState.questionsDirty) return;
  event.preventDefault();
});

async function showDashboard() {
  adminElements.login.hidden = true;
  adminElements.dashboard.hidden = false;
  adminElements.loading.hidden = false;
  adminElements.empty.hidden = true;

  try {
    await Promise.all([loadSubmissions(), loadCodes(), loadQuestionsEditor(), loadAdminPlanning()]);
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

async function loadQuestionsEditor() {
  const data = await adminFetch("/api/admin/questions");
  adminState.questions = Array.isArray(data.questions) ? data.questions : [];
  adminState.questionsDirty = false;
  renderQuestionEditor();
  setQuestionFeedback("");
}

function renderQuestionEditor() {
  adminElements.questionCount.textContent = adminState.questions.length;
  adminElements.questionPlural.hidden = adminState.questions.length === 1;
  adminElements.questionList.replaceChildren();

  adminState.questions.forEach((question, index) => {
    const editor = document.createElement("article");
    editor.className = "admin-question-editor";
    editor.innerHTML = `
      <div class="admin-question-editor__header">
        <span>Question ${index + 1}</span>
        <div class="admin-question-editor__controls">
          <button type="button" data-action="up" aria-label="Monter la question ${index + 1}">↑</button>
          <button type="button" data-action="down" aria-label="Descendre la question ${index + 1}">↓</button>
          <button type="button" data-action="remove">Supprimer</button>
        </div>
      </div>
      <label>Titre<input type="text" data-field="title" maxlength="300" required /></label>
      <label>Explication<textarea data-field="helper" rows="4" maxlength="5000"></textarea></label>
      <label>Texte indicatif de la réponse<input type="text" data-field="placeholder" maxlength="300" /></label>
      <label class="admin-question-editor__required"><input type="checkbox" data-field="required" /> Réponse obligatoire</label>
    `;

    const title = editor.querySelector('[data-field="title"]');
    const helper = editor.querySelector('[data-field="helper"]');
    const placeholder = editor.querySelector('[data-field="placeholder"]');
    const required = editor.querySelector('[data-field="required"]');
    title.value = question.title || "";
    helper.value = question.helper || "";
    placeholder.value = question.placeholder || "Ta réponse…";
    required.checked = question.required !== false;

    [title, helper, placeholder].forEach((input) => {
      input.addEventListener("input", () => {
        question[input.dataset.field] = input.value;
        markQuestionsDirty();
      });
    });
    required.addEventListener("change", () => {
      question.required = required.checked;
      markQuestionsDirty();
    });

    const up = editor.querySelector('[data-action="up"]');
    const down = editor.querySelector('[data-action="down"]');
    up.disabled = index === 0;
    down.disabled = index === adminState.questions.length - 1;
    up.addEventListener("click", () => moveQuestion(index, -1));
    down.addEventListener("click", () => moveQuestion(index, 1));
    editor.querySelector('[data-action="remove"]').addEventListener("click", () => removeQuestion(index));

    adminElements.questionList.appendChild(editor);
  });
}

function addQuestion() {
  adminState.questions.push({
    id: "",
    title: "",
    helper: "",
    placeholder: "Ta réponse…",
    required: true,
  });
  renderQuestionEditor();
  markQuestionsDirty();
  const lastEditor = adminElements.questionList.lastElementChild;
  lastEditor.scrollIntoView({ behavior: "smooth", block: "center" });
  lastEditor.querySelector('[data-field="title"]').focus({ preventScroll: true });
}

function removeQuestion(index) {
  if (adminState.questions.length === 1) {
    setQuestionFeedback("Le questionnaire doit conserver au moins une question.", true);
    return;
  }
  adminState.questions.splice(index, 1);
  renderQuestionEditor();
  markQuestionsDirty();
}

function moveQuestion(index, direction) {
  const destination = index + direction;
  if (destination < 0 || destination >= adminState.questions.length) return;
  const [question] = adminState.questions.splice(index, 1);
  adminState.questions.splice(destination, 0, question);
  renderQuestionEditor();
  markQuestionsDirty();
}

function markQuestionsDirty() {
  adminState.questionsDirty = true;
  setQuestionFeedback("Modifications non sauvegardées.");
}

async function saveQuestions() {
  const invalidIndex = adminState.questions.findIndex((question) => !question.title.trim());
  if (invalidIndex !== -1) {
    const editor = adminElements.questionList.children[invalidIndex];
    const input = editor.querySelector('[data-field="title"]');
    input.classList.add("is-invalid");
    input.focus();
    setQuestionFeedback("Chaque question doit avoir un titre.", true);
    return;
  }

  setAdminButtonLoading(adminElements.saveQuestions, true, "Sauvegarde…", "Sauvegarder les questions");
  try {
    const data = await adminFetch("/api/admin/questions", {
      method: "PUT",
      body: JSON.stringify({ questions: adminState.questions }),
    });
    adminState.questions = data.questions;
    adminState.questionsDirty = false;
    renderQuestionEditor();
    setQuestionFeedback("Les questions sont publiées immédiatement.", false, true);
  } catch (error) {
    if (error.message !== "SESSION_EXPIRED") setQuestionFeedback(error.message, true);
  } finally {
    setAdminButtonLoading(adminElements.saveQuestions, false, "Sauvegarde…", "Sauvegarder les questions");
  }
}

function setQuestionFeedback(message, error = false, success = false) {
  adminElements.questionFeedback.textContent = message;
  adminElements.questionFeedback.classList.toggle("is-error", error);
  adminElements.questionFeedback.classList.toggle("is-success", success);
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

async function loadAdminPlanning() {
  const data = await adminFetch("/api/admin/planning");
  adminState.planningSlots = Array.isArray(data.slots) ? data.slots : [];
  if (adminState.planningSlots.length) {
    adminState.planningMonth = adminMonthStart(adminDate(adminState.planningSlots[0].startDate));
  }
  renderAdminPlanning();
}

function renderAdminPlanning() {
  const slots = adminState.planningSlots;
  const takenCount = slots.filter((slot) => slot.taken).length;
  adminElements.planningTotal.textContent = slots.length;
  adminElements.planningOpen.textContent = slots.length - takenCount;
  adminElements.planningTaken.textContent = takenCount;
  adminElements.planningMonth.textContent = new Intl.DateTimeFormat("fr-FR", {
    month: "long", year: "numeric", timeZone: "UTC",
  }).format(adminState.planningMonth);
  adminElements.planningCalendar.replaceChildren();

  const first = adminMonthStart(adminState.planningMonth);
  const gridStart = adminAddDays(first, -((first.getUTCDay() + 6) % 7));
  const visibleMonth = first.getUTCMonth();
  for (let index = 0; index < 42; index += 1) {
    const date = adminAddDays(gridStart, index);
    const slot = adminSlotForDate(date);
    const day = document.createElement("button");
    day.type = "button";
    day.className = "sprint-day";
    day.dataset.date = adminISO(date);
    if (date.getUTCMonth() !== visibleMonth) day.classList.add("is-outside");

    let rangeContent = "";
    if (slot) {
      const offset = Math.round((date - adminDate(slot.startDate)) / 86400000);
      decorateAdminRange(day, offset, date);
      day.dataset.slotId = String(slot.id);
      day.classList.add(slot.taken ? "is-taken" : "is-open");
      const label = slot.taken
        ? (slot.participantName || slot.reservedBy || "Déjà pris")
        : `Session ${String(slot.id).padStart(2, "0")}`;
      rangeContent = `<span>${escapeAdminHtml(label)}</span>`;
      day.setAttribute("aria-label", `${adminLongRange(slot.startDate)} — ${slot.taken ? "déjà pris" : "disponible"}`);
      day.draggable = true;
      day.addEventListener("dragstart", (event) => startAdminPlanningDrag(event, slot, offset, day));
      day.addEventListener("dragend", endAdminPlanningDrag);
      day.addEventListener("click", () => {
        if (!adminState.planningJustDragged) togglePlanningSlot(slot);
      });
    } else {
      day.classList.add("is-empty");
    }
    day.addEventListener("dragover", (event) => {
      if (!adminState.planningDrag) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      previewAdminPlanningDrag(date);
    });
    day.addEventListener("drop", (event) => {
      event.preventDefault();
      moveAdminPlanningSlot(date);
    });
    day.innerHTML = `<span class="sprint-day__number">${date.getUTCDate()}</span>${slot ? `<span class="sprint-day__range">${rangeContent}</span>` : ""}`;
    adminElements.planningCalendar.appendChild(day);
  }
}

function startAdminPlanningDrag(event, slot, offset, day) {
  adminState.planningDrag = { slotId: slot.id, offset };
  day.classList.add("is-dragging");
  adminElements.planningCalendar.querySelectorAll(`[data-slot-id="${slot.id}"]`).forEach((cell) => cell.classList.add("is-drag-origin"));
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", String(slot.id));
}

function previewAdminPlanningDrag(targetDate) {
  const newStart = adminAddDays(targetDate, -adminState.planningDrag.offset);
  const invalid = adminPlanningOverlaps(adminState.planningDrag.slotId, newStart);
  clearAdminPlanningPreview();
  adminElements.planningCalendar.querySelectorAll(".sprint-day[data-date]").forEach((cell) => {
    const cellDate = adminDate(cell.dataset.date);
    if (cellDate < newStart || cellDate > adminAddDays(newStart, 4)) return;
    const offset = Math.round((cellDate - newStart) / 86400000);
    cell.classList.add("is-drag-preview");
    if (offset === 0 || cellDate.getUTCDay() === 1) cell.classList.add("is-preview-segment-start");
    if (offset === 4 || cellDate.getUTCDay() === 0) cell.classList.add("is-preview-segment-end");
    if (offset === 0) cell.classList.add("is-preview-start");
    if (offset === 4) cell.classList.add("is-preview-end");
    if (invalid) cell.classList.add("is-preview-invalid");
  });
  setPlanningFeedback(`${invalid ? "Chevauchement impossible" : "Aperçu"} · ${adminLongRange(adminISO(newStart))}`, invalid);
}

async function moveAdminPlanningSlot(targetDate) {
  if (!adminState.planningDrag) return;
  const { slotId, offset } = adminState.planningDrag;
  const newStart = adminAddDays(targetDate, -offset);
  if (adminPlanningOverlaps(slotId, newStart)) {
    setPlanningFeedback("Cette période chevauche déjà un autre sprint.", true);
    endAdminPlanningDrag();
    return;
  }
  endAdminPlanningDrag();
  try {
    const data = await adminFetch("/api/admin/planning", {
      method: "PATCH",
      body: JSON.stringify({ id: slotId, startDate: adminISO(newStart) }),
    });
    const index = adminState.planningSlots.findIndex((slot) => slot.id === slotId);
    adminState.planningSlots[index] = data.slot;
    adminState.planningMonth = adminMonthStart(newStart);
    renderAdminPlanning();
    setPlanningFeedback(`Période déplacée · ${adminLongRange(data.slot.startDate)}`, false, true);
  } catch (error) {
    if (error.message !== "SESSION_EXPIRED") setPlanningFeedback(error.message, true);
    await reloadPlanningQuietly();
  }
}

function endAdminPlanningDrag() {
  if (!adminState.planningDrag) return;
  adminElements.planningCalendar.querySelectorAll(".is-dragging, .is-drag-origin").forEach((cell) => cell.classList.remove("is-dragging", "is-drag-origin"));
  clearAdminPlanningPreview();
  adminState.planningDrag = null;
  adminState.planningJustDragged = true;
  window.setTimeout(() => { adminState.planningJustDragged = false; }, 180);
}

function clearAdminPlanningPreview() {
  adminElements.planningCalendar.querySelectorAll(".is-drag-preview, .is-preview-segment-start, .is-preview-segment-end, .is-preview-start, .is-preview-end, .is-preview-invalid")
    .forEach((cell) => cell.classList.remove("is-drag-preview", "is-preview-segment-start", "is-preview-segment-end", "is-preview-start", "is-preview-end", "is-preview-invalid"));
}

async function togglePlanningSlot(slot) {
  if (slot.reservedBy && slot.taken) {
    const identity = slot.participantName || slot.reservedBy;
    if (!window.confirm(`Libérer la réservation de ${identity} ?`)) return;
  }
  setPlanningFeedback("Mise à jour du statut…");
  try {
    const data = await adminFetch("/api/admin/planning", {
      method: "PATCH",
      body: JSON.stringify({ id: slot.id, taken: !slot.taken }),
    });
    const index = adminState.planningSlots.findIndex((item) => item.id === slot.id);
    adminState.planningSlots[index] = data.slot;
    renderAdminPlanning();
    setPlanningFeedback(data.slot.taken ? "La période est marquée comme déjà prise." : "La période est à nouveau disponible.", false, true);
    await loadSubmissions();
  } catch (error) {
    if (error.message !== "SESSION_EXPIRED") setPlanningFeedback(error.message, true);
  }
}

async function createPlanningSlot(event) {
  event.preventDefault();
  const startDate = adminElements.planningDate.value;
  if (!startDate) {
    setPlanningFeedback("Choisis le premier jour du sprint.", true);
    return;
  }
  const button = adminElements.planningForm.querySelector("button");
  button.disabled = true;
  setPlanningFeedback("Ajout de la période…");
  try {
    const data = await adminFetch("/api/admin/planning", {
      method: "POST",
      body: JSON.stringify({ startDate }),
    });
    adminState.planningSlots.push(data.slot);
    adminState.planningSlots.sort((a, b) => a.startDate.localeCompare(b.startDate));
    adminState.planningMonth = adminMonthStart(adminDate(startDate));
    adminElements.planningForm.reset();
    renderAdminPlanning();
    setPlanningFeedback(`Période ajoutée · ${adminLongRange(startDate)}`, false, true);
  } catch (error) {
    if (error.message !== "SESSION_EXPIRED") setPlanningFeedback(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function reloadPlanningQuietly() {
  try { await loadAdminPlanning(); } catch { /* Le prochain chargement réessaiera. */ }
}

function setPlanningFeedback(message, error = false, success = false) {
  adminElements.planningFeedback.textContent = message;
  adminElements.planningFeedback.classList.toggle("is-error", error);
  adminElements.planningFeedback.classList.toggle("is-success", success);
}

function adminPlanningOverlaps(slotId, start) {
  const end = adminAddDays(start, 4);
  return adminState.planningSlots.some((slot) => {
    if (slot.id === slotId) return false;
    const otherStart = adminDate(slot.startDate);
    const otherEnd = adminAddDays(otherStart, 4);
    return start <= otherEnd && end >= otherStart;
  });
}

function adminSlotForDate(value) {
  const iso = adminISO(value);
  return adminState.planningSlots.find((slot) => iso >= slot.startDate && iso <= adminISO(adminAddDays(adminDate(slot.startDate), 4)));
}

function decorateAdminRange(day, offset, value) {
  const starts = offset === 0 || value.getUTCDay() === 1;
  const ends = offset === 4 || value.getUTCDay() === 0;
  day.classList.add(starts ? "is-range-start" : ends ? "is-range-end" : "is-range-middle");
  if (starts && ends) day.classList.add("is-range-end");
  if (offset === 0) day.classList.add("is-sprint-start");
  if (offset === 4) day.classList.add("is-sprint-end");
}

function adminDate(value) { return new Date(`${value}T00:00:00Z`); }
function adminISO(value) { return value.toISOString().slice(0, 10); }
function adminAddDays(value, amount) { const result = new Date(value); result.setUTCDate(result.getUTCDate() + amount); return result; }
function adminMonthStart(value) { return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1)); }
function adminLongRange(startValue) {
  const start = adminDate(startValue);
  const end = adminAddDays(start, 4);
  const first = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(start);
  const last = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(end);
  return `Du ${first} au ${last}`;
}

function renderSubmissions(query = "") {
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = adminState.submissions.filter((submission) => {
    const participant = submission.participant || {};
    const searchable = `${submission.id || ""} ${submission.accessCode || ""} ${participant.firstName || ""} ${participant.lastName || ""} ${participant.email || ""} ${participant.phone || ""}`.toLowerCase();
    return searchable.includes(normalizedQuery);
  });

  adminElements.count.textContent = filtered.length;
  adminElements.plural.hidden = filtered.length === 1;
  adminElements.list.replaceChildren();
  adminElements.empty.hidden = filtered.length !== 0;

  filtered.forEach((submission) => adminElements.list.appendChild(createSubmission(submission)));
}

function createSubmission(submission) {
  const participant = submission.participant || {};
  const participantName = [participant.firstName, participant.lastName].filter(Boolean).join(" ") || "Profil non renseigné";
  const details = document.createElement("details");
  details.className = "submission";
  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="submission__identity">
      <small>Participant</small>
      <strong>${escapeAdminHtml(participantName)}</strong>
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
  const participantElement = document.createElement("div");
  participantElement.className = "submission__participant";
  participantElement.innerHTML = `
    <div><small>Prénom</small><strong>${escapeAdminHtml(participant.firstName || "—")}</strong></div>
    <div><small>Nom</small><strong>${escapeAdminHtml(participant.lastName || "—")}</strong></div>
    <div><small>Téléphone</small><a href="${participant.phone ? `tel:${escapeAdminHtml(participant.phone)}` : "#"}">${escapeAdminHtml(participant.phone || "—")}</a></div>
    <div><small>Email</small><a href="${participant.email ? `mailto:${escapeAdminHtml(participant.email)}` : "#"}">${escapeAdminHtml(participant.email || "—")}</a></div>
    <div><small>ID de réponse</small><strong>${escapeAdminHtml(submission.id || "—")}</strong></div>
    <div><small>Période du sprint</small><strong>${submission.sprint ? escapeAdminHtml(adminLongRange(submission.sprint.startDate)) : "Non réservée"}</strong></div>
  `;
  answersContainer.appendChild(participantElement);
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
