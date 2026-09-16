const planningToken = sessionStorage.getItem("nxt_access_token");

if (!planningToken) {
  window.location.replace("/");
} else {
  initializePlanning();
}

function initializePlanning() {
  const state = {
    slots: [],
    selectedId: null,
    displayMonth: new Date(),
    dragging: null,
    reserved: false,
  };
  const calendar = document.querySelector("#planning-calendar");
  const monthLabel = document.querySelector("#planning-month");
  const summary = document.querySelector("#planning-summary");
  const errorElement = document.querySelector("#planning-error");
  const reserveButton = document.querySelector("#reserve-slot");

  loadPlanning();

  async function loadPlanning() {
    try {
      const response = await fetch("/api/planning", {
        headers: { Authorization: `Bearer ${planningToken}` },
        cache: "no-store",
      });
      const data = await response.json();
      if (response.status === 401) {
        sessionStorage.removeItem("nxt_access_token");
        window.location.replace("/");
        return;
      }
      if (response.status === 403) {
        window.location.replace("/questionnaire.html");
        return;
      }
      if (!response.ok) throw new Error(data.message || "Impossible de charger le planning.");
      state.slots = Array.isArray(data.slots) ? data.slots : [];
      const initial = data.reservation || state.slots.find((slot) => !slot.taken);
      if (initial) {
        state.displayMonth = monthStart(dateFromISO(initial.startDate));
      }
      if (data.reservation) {
        state.selectedId = data.reservation.id;
        state.reserved = true;
        summary.textContent = longRange(data.reservation.startDate);
        reserveButton.disabled = false;
        reserveButton.querySelector("span:first-child").textContent = "Découvrir la suite";
      }
      render();
    } catch (error) {
      errorElement.textContent = error.message === "Failed to fetch" ? "Le serveur ne répond pas." : error.message;
    }
  }

  function render() {
    const label = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric", timeZone: "UTC" }).format(state.displayMonth);
    monthLabel.textContent = label;
    calendar.replaceChildren();
    const first = monthStart(state.displayMonth);
    const gridStart = addDays(first, -((first.getUTCDay() + 6) % 7));
    const visibleMonth = first.getUTCMonth();

    for (let index = 0; index < 42; index += 1) {
      const date = addDays(gridStart, index);
      const slot = slotForDateFrom(state.slots, date);
      const day = document.createElement("button");
      day.type = "button";
      day.className = "sprint-day";
      day.dataset.date = isoDate(date);
      if (date.getUTCMonth() !== visibleMonth) day.classList.add("is-outside");

      let rangeContent = "";
      if (slot) {
        const offset = dayOffset(slot, date);
        decorateRange(day, offset);
        day.dataset.slotId = String(slot.id);
        day.classList.add(slot.taken && !slot.mine ? "is-taken" : "is-open");
        if (state.selectedId === slot.id) day.classList.add("is-selected");
        rangeContent = `<span>${slot.mine ? "Ton sprint" : `Session ${String(slot.id).padStart(2, "0")}`}</span>`;
        day.setAttribute("aria-label", `${longRange(slot.startDate)} — ${slot.taken && !slot.mine ? "déjà pris" : "disponible"}`);
        if (!slot.taken && !state.reserved) {
          day.draggable = true;
          day.addEventListener("click", () => selectSlot(slot.id));
          day.addEventListener("dragstart", (event) => startDragging(event, slot, offset, day));
          day.addEventListener("dragend", endDragging);
        }
      } else {
        day.classList.add("is-empty");
        day.setAttribute("aria-label", formatDate(date));
      }

      day.addEventListener("dragover", (event) => {
        if (!state.dragging) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        previewDrag(date);
      });
      day.addEventListener("drop", (event) => {
        event.preventDefault();
        dropOn(date);
      });
      day.innerHTML = `<span class="sprint-day__number">${date.getUTCDate()}</span>${slot ? `<span class="sprint-day__range">${rangeContent}</span>` : ""}`;
      calendar.appendChild(day);
    }
  }

  function selectSlot(id) {
    state.selectedId = id;
    const slot = state.slots.find((item) => item.id === id);
    summary.textContent = longRange(slot.startDate);
    reserveButton.disabled = false;
    render();
  }

  function startDragging(event, slot, offset, day) {
    state.selectedId = slot.id;
    state.dragging = { slotId: slot.id, offset };
    summary.textContent = longRange(slot.startDate);
    reserveButton.disabled = false;
    day.classList.add("is-dragging");
    calendar.querySelectorAll(`[data-slot-id="${slot.id}"]`).forEach((cell) => cell.classList.add("is-selected", "is-drag-origin"));
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(slot.id));
  }

  function previewDrag(targetDate) {
    const newStart = addDays(targetDate, -state.dragging.offset);
    const invalid = overlapsAnother(state.dragging.slotId, newStart);
    clearPreview();
    calendar.querySelectorAll(".sprint-day[data-date]").forEach((cell) => {
      const cellDate = dateFromISO(cell.dataset.date);
      if (cellDate < newStart || cellDate > addDays(newStart, 4)) return;
      const offset = Math.round((cellDate - newStart) / 86400000);
      cell.classList.add("is-drag-preview");
      decoratePreview(cell, cellDate, offset);
      if (invalid) cell.classList.add("is-preview-invalid");
    });
    summary.textContent = `${invalid ? "Indisponible" : "Aperçu"} · ${longRange(isoDate(newStart))}`;
  }

  function dropOn(targetDate) {
    if (!state.dragging) return;
    const slot = state.slots.find((item) => item.id === state.dragging.slotId);
    const newStart = addDays(targetDate, -state.dragging.offset);
    if (overlapsAnother(slot.id, newStart)) {
      errorElement.textContent = "Cette période chevauche déjà un autre sprint.";
      endDragging();
      return;
    }
    slot.startDate = isoDate(newStart);
    slot.endDate = isoDate(addDays(newStart, 4));
    state.displayMonth = monthStart(newStart);
    errorElement.textContent = "";
    endDragging();
    summary.textContent = longRange(slot.startDate);
    render();
  }

  function overlapsAnother(slotId, start) {
    const end = addDays(start, 4);
    return state.slots.some((slot) => {
      if (slot.id === slotId) return false;
      const otherStart = dateFromISO(slot.startDate);
      const otherEnd = addDays(otherStart, 4);
      return start <= otherEnd && end >= otherStart;
    });
  }

  function endDragging() {
    clearPreview();
    calendar.querySelectorAll(".is-dragging, .is-drag-origin").forEach((cell) => cell.classList.remove("is-dragging", "is-drag-origin"));
    state.dragging = null;
    const selected = state.slots.find((slot) => slot.id === state.selectedId);
    if (selected) summary.textContent = longRange(selected.startDate);
  }

  function clearPreview() {
    calendar.querySelectorAll(".is-drag-preview, .is-preview-segment-start, .is-preview-segment-end, .is-preview-start, .is-preview-end, .is-preview-invalid")
      .forEach((cell) => cell.classList.remove("is-drag-preview", "is-preview-segment-start", "is-preview-segment-end", "is-preview-start", "is-preview-end", "is-preview-invalid"));
  }

  reserveButton.addEventListener("click", async () => {
    if (state.reserved) {
      window.location.assign("/experience.html");
      return;
    }
    const slot = state.slots.find((item) => item.id === state.selectedId);
    if (!slot) return;
    errorElement.textContent = "";
    setPlanningButton(true, "Réservation…");
    try {
      const response = await fetch("/api/planning/reserve", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${planningToken}` },
        body: JSON.stringify({ slotId: slot.id, startDate: slot.startDate }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Impossible de réserver cette période.");
      state.reserved = true;
      window.location.assign("/experience.html");
    } catch (error) {
      errorElement.textContent = error.message === "Failed to fetch" ? "Le serveur ne répond pas." : error.message;
      setPlanningButton(false, "Réserver cette période");
      if (error.message.includes("réservée") || error.message.includes("chevauche")) loadPlanning();
    }
  });

  document.querySelectorAll("[data-month-shift]").forEach((button) => {
    button.addEventListener("click", () => {
      state.displayMonth = new Date(Date.UTC(state.displayMonth.getUTCFullYear(), state.displayMonth.getUTCMonth() + Number(button.dataset.monthShift), 1));
      render();
    });
  });

  function setPlanningButton(loading, label) {
    reserveButton.disabled = loading;
    reserveButton.querySelector("span:first-child").textContent = label;
  }
}

function dateFromISO(value) { return new Date(`${value}T00:00:00Z`); }
function isoDate(value) { return value.toISOString().slice(0, 10); }
function addDays(value, amount) { const result = new Date(value); result.setUTCDate(result.getUTCDate() + amount); return result; }
function monthStart(value) { return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1)); }
function formatDate(value) { return new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeZone: "UTC" }).format(value); }
function longRange(startValue) {
  const start = dateFromISO(startValue);
  const end = addDays(start, 4);
  const first = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(start);
  const last = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(end);
  return `Du ${first} au ${last}`;
}
function dayOffset(slot, value) { return Math.round((value - dateFromISO(slot.startDate)) / 86400000); }
function slotForDateFrom(slots, value) {
  const iso = isoDate(value);
  return slots.find((slot) => iso >= slot.startDate && iso <= isoDate(addDays(dateFromISO(slot.startDate), 4)));
}
function decorateRange(day, offset) {
  const weekday = dateFromISO(day.dataset.date).getUTCDay();
  const starts = offset === 0 || weekday === 1;
  const ends = offset === 4 || weekday === 0;
  day.classList.add(starts ? "is-range-start" : ends ? "is-range-end" : "is-range-middle");
  if (starts && ends) day.classList.add("is-range-end");
  if (offset === 0) day.classList.add("is-sprint-start");
  if (offset === 4) day.classList.add("is-sprint-end");
}
function decoratePreview(day, value, offset) {
  if (offset === 0 || value.getUTCDay() === 1) day.classList.add("is-preview-segment-start");
  if (offset === 4 || value.getUTCDay() === 0) day.classList.add("is-preview-segment-end");
  if (offset === 0) day.classList.add("is-preview-start");
  if (offset === 4) day.classList.add("is-preview-end");
}
