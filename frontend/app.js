const $ = (selector) => document.querySelector(selector);
const chatMessages = $("#chat-messages");
let conversationId = localStorage.getItem("wayfarerConversationId");
let lastItinerary = null;

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
}

function formatAnswer(value) {
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function setLoading(button, loading, label) {
  if (loading) {
    button.dataset.label = button.innerHTML;
    button.innerHTML = `<span class="spinner"></span>${escapeHtml(label)}`;
    button.classList.add("loading");
    button.disabled = true;
  } else {
    button.innerHTML = button.dataset.label || label;
    button.classList.remove("loading");
    button.disabled = false;
  }
}

function addChatMessage(question, answer, citations = []) {
  const user = document.createElement("div");
  user.className = "user-message";
  user.innerHTML = `<p>${formatAnswer(question)}</p>`;
  const assistant = document.createElement("div");
  assistant.className = "assistant-message";
  const sources = citations.length
    ? `<ul class="citation-list">${citations.map((source) => `<li>[${escapeHtml(source.label)}] ${escapeHtml(source.source)}${source.page ? ` · page ${source.page}` : ""}${source.section ? ` · ${escapeHtml(source.section)}` : ""}</li>`).join("")}</ul>`
    : "";
  assistant.innerHTML = `<span class="avatar">W</span><div><p>${formatAnswer(answer)}</p>${sources}<small>YOUR WAYFARER GUIDE</small></div>`;
  chatMessages.append(user, assistant);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#question");
  const question = input.value.trim();
  if (!question) return;
  const button = event.currentTarget.querySelector("button");
  setLoading(button, true, "Thinking…");
  try {
    const result = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, model: $("#model-select").value, conversation_id: conversationId })
    });
    conversationId = result.conversation_id;
    localStorage.setItem("wayfarerConversationId", conversationId);
    addChatMessage(question, result.answer, result.citations);
    input.value = "";
  } catch (error) {
    addChatMessage(question, error.message);
  } finally {
    setLoading(button, false, "↑");
    button.textContent = "↑";
  }
});

document.querySelectorAll(".suggestions button").forEach((button) => {
  button.addEventListener("click", () => {
    $("#question").value = button.dataset.question;
    $("#question").focus();
  });
});

$("#itinerary-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const payload = Object.fromEntries(values.entries());
  payload.travelers = Number(payload.travelers);
  payload.budget_inr = Number(payload.budget_inr);
  payload.interests = values.getAll("interests");
  payload.model = $("#model-select").value;
  setLoading(submitButton, true, "Planning your trip…");
  try {
    lastItinerary = await api("/api/itinerary/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    renderItinerary(lastItinerary);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setLoading(submitButton, false, "Create my itinerary ↗");
  }
});

function renderItinerary(plan) {
  const section = $("#itinerary-result");
  const days = plan.days.map((day) => `
    <article class="day-card"><h3>Day ${day.day} <span class="result-meta">${escapeHtml(day.date)}</span></h3>
      <p><b>Morning</b><br>${escapeHtml(day.morning)}</p>
      <p><b>Afternoon</b><br>${escapeHtml(day.afternoon)}</p>
      <p><b>Evening</b><br>${escapeHtml(day.evening)}</p></article>`).join("");
  const budget = Object.entries({
    Transport: plan.budget.transport, Accommodation: plan.budget.accommodation,
    Food: plan.budget.food, Activities: plan.budget.activities
  }).map(([label, amount]) => `<div class="budget-item"><small>${label}</small><b>₹${Number(amount).toLocaleString("en-IN")}</b></div>`).join("");
  const citations = plan.citations.length
    ? `<ul class="citation-list">${plan.citations.map((source) => `<li>[${escapeHtml(source.label)}] ${escapeHtml(source.source)}${source.page ? ` · page ${source.page}` : ""}${source.section ? ` · ${escapeHtml(source.section)}` : ""}</li>`).join("")}</ul>`
    : "<p class=\"result-note\">No destination documents were available to cite for this plan.</p>";
  const limitations = plan.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  section.innerHTML = `<div class="result-header"><div><div class="eyebrow">MADE FOR YOU</div><h2>Your ${escapeHtml(plan.destination)} itinerary</h2><div class="result-meta">${plan.days.length} thoughtful ${plan.days.length === 1 ? "day" : "days"} · estimates shown in INR</div></div><button id="save-trip" class="secondary-button">Save this trip ♡</button></div>
    <div class="day-grid">${days}</div><h3>Budget plan <span class="result-meta">· total ₹${Number(plan.budget.total).toLocaleString("en-IN")}</span></h3><div class="budget-grid">${budget}</div>
    <p class="result-note">${escapeHtml(plan.budget.note)}</p><div class="form-row"><div><b>Getting there</b><p class="result-note">${escapeHtml(plan.transport_suggestion)}</p></div><div><b>Stay</b><p class="result-note">${escapeHtml(plan.accommodation_suggestion)}</p></div></div>
    <div class="form-row"><div><b>Travel tips</b><ul class="result-note">${plan.travel_tips.map((tip) => `<li>${escapeHtml(tip)}</li>`).join("")}</ul></div><div><b>Sources</b>${citations}</div></div>
    <ul class="limitation">${limitations}</ul>`;
  section.hidden = false;
  section.scrollIntoView({ behavior: "smooth", block: "start" });
  $("#save-trip").addEventListener("click", saveItinerary);
}

async function saveItinerary() {
  const form = new FormData($("#itinerary-form"));
  const title = `${form.get("destination")} · ${form.get("start_date")}`;
  try {
    await api("/api/trips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, destination: form.get("destination"), itinerary: lastItinerary })
    });
    showToast("Trip saved to your notebook.");
    await loadTrips();
  } catch (error) { showToast(error.message, true); }
}

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $("#upload-status");
  const data = new FormData(form);
  const destination = data.get("destination");
  if (!destination) data.delete("destination");
  status.textContent = "Uploading and indexing with your local embedding model…";
  try {
    const result = await api("/api/documents/ingest", { method: "POST", body: data });
    status.textContent = `Indexed ${result.total_chunks} chunks from ${result.indexed.length} file(s).`;
    form.reset();
    await loadDestinations();
  } catch (error) { status.textContent = error.message; }
});

async function loadDestinations() {
  const container = $("#destination-chips");
  try {
    const result = await api("/api/destinations");
    container.innerHTML = result.destinations.length
      ? result.destinations.map((name) => `<span class="destination-chip">${escapeHtml(name)}</span>`).join("")
      : '<span class="result-note">No guides indexed yet. Add documents above to get destination-specific answers.</span>';
  } catch (error) { container.textContent = error.message; }
}

async function loadHealth() {
  const dot = $("#health-dot");
  const label = $("#health-label");
  try {
    const health = await api("/health");
    const ollama = health.ollama;
    dot.classList.add(ollama.available && ollama.chat_model_installed && ollama.embedding_model_installed ? "online" : "offline");
    label.textContent = !ollama.available ? ollama.error
      : !ollama.chat_model_installed ? `Chat model ${$("#model-select").value} is not installed`
        : !ollama.embedding_model_installed ? "Embedding model missing — see setup instructions"
          : `Local assistant ready · ${health.vector_database.indexed_chunks} indexed chunks`;
    const models = await api("/api/models");
    [...$("#model-select").options].forEach((option) => {
      option.disabled = !models.available_models.includes(option.value);
    });
    if (!models.available_models.includes($("#model-select").value) && models.default_model) {
      $("#model-select").value = models.default_model;
    }
  } catch (error) {
    dot.classList.add("offline");
    label.textContent = error.message;
  }
}

async function loadTrips() {
  const container = $("#saved-trips");
  try {
    const result = await api("/api/trips");
    $("#saved-count").textContent = result.length;
    container.innerHTML = result.length ? result.map((trip) => `
      <article class="saved-card"><h3>${escapeHtml(trip.title)}</h3><p>${escapeHtml(trip.destination)} · saved ${escapeHtml(trip.created_at)}</p>
      <div class="saved-actions"><button class="secondary-button" data-open-trip="${trip.id}">View trip</button><button class="secondary-button" data-delete-trip="${trip.id}">Delete</button></div></article>`).join("")
      : '<p class="result-note">Your saved trips will appear here.</p>';
    container.querySelectorAll("[data-open-trip]").forEach((button) => button.addEventListener("click", async () => {
      try {
        const saved = await api(`/api/trips/${button.dataset.openTrip}`);
        switchView("planner");
        lastItinerary = saved.itinerary;
        renderItinerary(saved.itinerary);
      } catch (error) { showToast(error.message, true); }
    }));
    container.querySelectorAll("[data-delete-trip]").forEach((button) => button.addEventListener("click", async () => {
      try { await api(`/api/trips/${button.dataset.deleteTrip}`, { method: "DELETE" }); await loadTrips(); }
      catch (error) { showToast(error.message, true); }
    }));
  } catch (error) { container.textContent = error.message; }
}

async function loadConversation() {
  if (!conversationId) return;
  try {
    const result = await api(`/api/conversations/${encodeURIComponent(conversationId)}`);
    result.messages.forEach((message) => addChatMessage(message.question, message.answer, message.citations));
  } catch (error) {
    showToast(`Could not restore chat history: ${error.message}`, true);
  }
}

function switchView(view) {
  const saved = view === "saved";
  $("#planner-view").hidden = saved;
  $("#sources-panel").hidden = saved;
  $("#saved-view").hidden = !saved;
  document.querySelectorAll(".nav-link").forEach((link) => link.classList.toggle("active", link.dataset.view === view));
}

document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => {
  switchView(button.dataset.view);
  if (button.dataset.view === "saved") loadTrips();
}));
$("#back-to-planner").addEventListener("click", () => switchView("planner"));

const today = new Date();
const tomorrow = new Date(today);
tomorrow.setDate(today.getDate() + 1);
$("#itinerary-form [name=start_date]").value = today.toISOString().slice(0, 10);
$("#itinerary-form [name=end_date]").value = tomorrow.toISOString().slice(0, 10);
loadHealth();
loadDestinations();
loadTrips();
loadConversation();
