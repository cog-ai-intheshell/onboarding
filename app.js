const isQuestionnairePage = document.body.classList.contains("questionnaire-page");

function setButtonLoading(button, loading, loadingLabel, normalLabel) {
  button.disabled = loading;
  button.querySelector("span:first-child").textContent = loading ? loadingLabel : normalLabel;
}

if (isQuestionnairePage) {
  initializeQuestionnairePage();
} else {
  initializeAccessPage();
}

function initializeAccessPage() {
  const accessForm = document.querySelector("#access-form");
  const accessCode = document.querySelector("#access-code");
  const accessError = document.querySelector("#access-error");

  if (new URLSearchParams(window.location.search).get("saved") === "1") {
    accessError.classList.add("is-success");
    accessError.textContent = "Tes réponses sont sauvegardées. Reviens quand tu veux avec ton code.";
  }

  accessCode.addEventListener("input", () => {
    accessCode.value = accessCode.value.toUpperCase();
    accessCode.classList.remove("is-valid", "is-invalid");
    accessError.classList.remove("is-success");
    accessError.textContent = "";
  });

  accessForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = accessCode.value.trim().toUpperCase();
    const button = accessForm.querySelector("button");
    accessError.textContent = "";
    accessCode.classList.remove("is-valid", "is-invalid");

    if (!code) {
      accessCode.classList.add("is-invalid");
      accessError.textContent = "Entre ton code pour continuer.";
      accessCode.focus();
      return;
    }

    setButtonLoading(button, true, "Vérification…", "Commencer");
    try {
      const response = await fetch("/api/validate-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await response.json();
      if (!response.ok || !data.valid) throw new Error(data.message || "Ce code n’est pas valide.");

      accessCode.classList.add("is-valid");
      sessionStorage.setItem("nxt_access_token", data.accessToken);
      window.setTimeout(() => window.location.assign("/questionnaire.html"), 220);
    } catch (error) {
      accessCode.classList.add("is-invalid");
      accessError.textContent = error.message === "Failed to fetch"
        ? "Le serveur ne répond pas. Lance le site avec server.py."
        : error.message;
      setButtonLoading(button, false, "Vérification…", "Commencer");
    }
  });

  fetch("/api/questions", { cache: "no-store" })
    .then((response) => response.ok ? response.json() : Promise.reject())
    .then((data) => {
      if (Array.isArray(data.questions)) {
        document.querySelector("#hero-question-count").textContent = data.questions.length;
      }
    })
    .catch(() => {});
}

function initializeQuestionnairePage() {
  const accessToken = sessionStorage.getItem("nxt_access_token");
  if (!accessToken) {
    window.location.replace("/");
    return;
  }

  const state = {
    questions: [],
    answers: loadDraft(),
    accessToken,
  };
  const elements = {
    questionnaire: document.querySelector("#questionnaire"),
    loadingState: document.querySelector("#loading-state"),
    questionForm: document.querySelector("#question-form"),
    questionList: document.querySelector("#question-list"),
    questionTemplate: document.querySelector("#question-template"),
    submitButton: document.querySelector("#submit-button"),
    submitError: document.querySelector("#submit-error"),
    saveDraftButton: document.querySelector("#save-draft-button"),
    saveStatus: document.querySelector("#save-status"),
    success: document.querySelector("#success"),
  };

  restoreDraftAndQuestions();

  async function restoreDraftAndQuestions() {
    try {
      const response = await fetch("/api/draft", {
        headers: { Authorization: `Bearer ${state.accessToken}` },
        cache: "no-store",
      });
      if (response.status === 401) {
        sessionStorage.removeItem("nxt_access_token");
        window.location.replace("/");
        return;
      }
      if (response.ok) {
        const data = await response.json();
        if (data.answers && typeof data.answers === "object") {
          state.answers = { ...state.answers, ...data.answers };
          saveDraft(state.answers);
        }
      }
    } catch {
      // Le brouillon local reste disponible si le serveur est momentanément inaccessible.
    }
    await loadQuestions();
  }

  async function loadQuestions() {
    try {
      const response = await fetch("/api/questions", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || !Array.isArray(data.questions) || data.questions.length === 0) {
        throw new Error(data.message || "Le questionnaire est momentanément indisponible.");
      }
      state.questions = data.questions;
      renderQuestions();
      elements.loadingState.hidden = true;
      elements.questionForm.hidden = false;
    } catch (error) {
      elements.loadingState.innerHTML = `<p class="loading-error">${escapeHtml(error.message || "Impossible de charger le questionnaire.")}</p>`;
    }
  }

  function renderQuestions() {
    elements.questionList.replaceChildren();
    state.questions.forEach((question, index) => {
      const row = elements.questionTemplate.content.firstElementChild.cloneNode(true);
      const input = row.querySelector(".answer-input");
      const label = row.querySelector(".question-title");

      row.dataset.questionId = question.id;
      label.textContent = question.title;
      label.htmlFor = `answer-${question.id}`;
      row.querySelector(".question-helper").textContent = question.helper || "Réponds librement, avec tes propres mots.";
      input.id = `answer-${question.id}`;
      input.name = question.id;
      input.placeholder = question.placeholder || "Ta réponse…";
      input.required = question.required !== false;
      input.value = state.answers[question.id] || "";
      markComplete(row, isAnswerValid(question, input.value));

      input.addEventListener("input", () => handleAnswerInput(row, question, input));
      input.addEventListener("blur", () => validateRow(row, question, input.value, false));
      elements.questionList.appendChild(row);
    });
  }

  function handleAnswerInput(row, question, input) {
    state.answers[question.id] = input.value.trim();
    row.classList.remove("is-invalid");
    row.querySelector(".answer-error").textContent = "";
    markComplete(row, isAnswerValid(question, input.value));
    saveDraft(state.answers);
  }

  function isAnswerValid(question, value) {
    return question.required === false || value.trim().length > 0;
  }

  function markComplete(row, complete) {
    row.classList.toggle("is-complete", complete);
  }

  function validateRow(row, question, value, showEmptyAsError = true) {
    const valid = isAnswerValid(question, value);
    const shouldShow = !valid && (showEmptyAsError || value.trim() !== "");
    row.classList.toggle("is-invalid", shouldShow);
    row.querySelector(".answer-error").textContent = shouldShow
      ? "Cette réponse est requise."
      : "";
    return valid;
  }

  function validateAllQuestions() {
    let firstInvalid = null;
    state.questions.forEach((question) => {
      const row = elements.questionList.querySelector(`[data-question-id="${CSS.escape(question.id)}"]`);
      const value = row.querySelector("textarea").value;
      if (!validateRow(row, question, value) && !firstInvalid) firstInvalid = row;
    });
    if (firstInvalid) {
      firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
      firstInvalid.querySelector("textarea").focus({ preventScroll: true });
    }
    return firstInvalid === null;
  }

  elements.questionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    elements.submitError.textContent = "";
    if (!validateAllQuestions()) {
      elements.submitError.textContent = "Certaines réponses sont encore incomplètes.";
      return;
    }

    setButtonLoading(elements.submitButton, true, "Envoi en cours…", "Envoyer mes réponses");
    try {
      const response = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.accessToken}` },
        body: JSON.stringify({ answers: state.answers }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Impossible d’enregistrer tes réponses.");

      localStorage.removeItem("nxt_onboarding_draft");
      sessionStorage.removeItem("nxt_access_token");
      window.location.assign("/experience.html");
    } catch (error) {
      elements.submitError.textContent = error.message === "Failed to fetch"
        ? "Connexion impossible. Vérifie le serveur puis réessaie."
        : error.message;
    } finally {
      setButtonLoading(elements.submitButton, false, "Envoi en cours…", "Envoyer mes réponses");
    }
  });

  elements.saveDraftButton.addEventListener("click", async () => {
    elements.saveStatus.textContent = "";
    elements.submitError.textContent = "";
    setButtonLoading(elements.saveDraftButton, true, "Sauvegarde…", "Sauvegarder mes réponses et revenir plus tard");
    try {
      const response = await fetch("/api/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.accessToken}` },
        body: JSON.stringify({ answers: state.answers }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Impossible de sauvegarder tes réponses.");

      saveDraft(state.answers);
      elements.saveStatus.textContent = "Tes réponses sont bien sauvegardées.";
      window.setTimeout(() => window.location.assign("/?saved=1"), 650);
    } catch (error) {
      elements.submitError.textContent = error.message === "Failed to fetch"
        ? "Connexion impossible. Vérifie le serveur puis réessaie."
        : error.message;
      setButtonLoading(elements.saveDraftButton, false, "Sauvegarde…", "Sauvegarder mes réponses et revenir plus tard");
    }
  });
}

function loadDraft() {
  try {
    return JSON.parse(localStorage.getItem("nxt_onboarding_draft")) || {};
  } catch {
    return {};
  }
}

function saveDraft(answers) {
  localStorage.setItem("nxt_onboarding_draft", JSON.stringify(answers));
}

function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = value;
  return element.innerHTML;
}
