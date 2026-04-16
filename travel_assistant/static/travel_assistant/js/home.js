const cityButtons = Array.from(document.querySelectorAll(".city-pill"));
const planner = document.querySelector(".planner");
const activeCityLabel = document.querySelector("#active-city-label");
const activeCitySubtitle = document.querySelector("#active-city-subtitle");
const chatLog = document.querySelector("#chat-log");
const starterState = document.querySelector("#starter-state");
const starterPrompts = document.querySelector("#starter-prompts");
const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message");
const sendButton = document.querySelector("#send-button");
const errorLine = document.querySelector("#error-line");
const downloadPlanButton = document.querySelector("#download-plan-button");
const planModal = document.querySelector("#plan-modal");
const closePlanModalButton = document.querySelector("#close-plan-modal");
const startSubscriptionButton = document.querySelector("#start-subscription");
const cityMenuToggle = document.querySelector("#city-menu-toggle");
const cityMenuPanel = document.querySelector("#city-menu-panel");
const cityMenuItems = Array.from(document.querySelectorAll(".city-menu-item"));
const cityOptions = JSON.parse(document.querySelector("#city-options-data").textContent);
const CHAT_STORAGE_KEY = "llama_city_conversations_v1";

let selectedCity = cityButtons[0]?.dataset.city || "san-francisco";
let cityConversations = {};

function csrfToken() {
  const input = chatForm.querySelector("input[name=csrfmiddlewaretoken]");
  return input?.value || "";
}

function appendBubble(text, who) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${who === "user" ? "bubble-user" : "bubble-assistant"}`;
  if (who === "assistant") {
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

function getConversation(citySlug = selectedCity) {
  if (!citySlug) {
    return [];
  }
  if (!Array.isArray(cityConversations[citySlug])) {
    cityConversations[citySlug] = [];
  }
  return cityConversations[citySlug];
}

function saveConversationState() {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(cityConversations));
  } catch (_error) {
    // Ignore storage errors in private mode/quota limits.
  }
}

function loadConversationState() {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    const normalized = {};
    Object.entries(parsed).forEach(([slug, turns]) => {
      if (!cityOptions[slug] || !Array.isArray(turns)) {
        return;
      }
      normalized[slug] = turns
        .filter((turn) => turn && (turn.role === "user" || turn.role === "assistant") && typeof turn.content === "string")
        .map((turn) => ({ role: turn.role, content: turn.content }));
    });
    return normalized;
  } catch (_error) {
    return {};
  }
}

function renderStarterState() {
  chatLog.innerHTML = `
    <section id="starter-state" class="starter-state">
      <div id="starter-prompts" class="starter-prompts"></div>
    </section>
  `;
}

function renderChatForSelectedCity() {
  chatLog.innerHTML = "";
  const turns = getConversation();
  if (!turns.length) {
    renderStarterState();
    renderStarterPrompts();
    return;
  }
  turns.forEach((turn) => appendBubble(turn.content, turn.role));
}

function renderMarkdown(markdownText) {
  if (!window.marked || !window.DOMPurify) {
    const fallback = document.createElement("div");
    fallback.textContent = markdownText;
    return fallback.innerHTML;
  }
  const rawHtml = window.marked.parse(markdownText, { breaks: true });
  return window.DOMPurify.sanitize(rawHtml);
}

function setPlanModalOpen(isOpen) {
  planModal.setAttribute("aria-hidden", isOpen ? "false" : "true");
}

function setCityMenuOpen(isOpen) {
  cityMenuPanel.classList.toggle("is-open", isOpen);
  cityMenuPanel.setAttribute("aria-hidden", isOpen ? "false" : "true");
  cityMenuToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
}

function setSubmittingState(isSubmitting) {
  sendButton.disabled = isSubmitting;
  sendButton.classList.toggle("is-loading", isSubmitting);
  sendButton.textContent = isSubmitting ? "Writing..." : "Ask";
  downloadPlanButton.disabled = isSubmitting;
  cityMenuToggle.disabled = isSubmitting;
  cityButtons.forEach((button) => {
    button.disabled = isSubmitting;
  });
  cityMenuItems.forEach((item) => {
    item.disabled = isSubmitting;
  });
}

function openPlanPremiumInterstitial() {
  setPlanModalOpen(true);
}

async function streamAssistantReply(message) {
  const citySlugAtRequestStart = selectedCity;
  const cityTurns = getConversation(citySlugAtRequestStart);
  const response = await fetch("/api/chat/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify({
      city: citySlugAtRequestStart,
      message,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error("Assistant unavailable right now. Try again.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let eventName = "";
  let assistantText = "";
  let assistantBubble = null;
  let hasStarted = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";

    for (const frame of frames) {
      const lines = frame.split("\n");
      let dataLine = "";
      eventName = "";
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        }
        if (line.startsWith("data:")) {
          dataLine += line.slice(5).trim();
        }
      }
      if (!dataLine) {
        continue;
      }

      const payload = JSON.parse(dataLine);
      if ((eventName === "start" || eventName === "delta") && !hasStarted) {
        cityTurns.push({ role: "user", content: message });
        saveConversationState();
        if (selectedCity === citySlugAtRequestStart) {
          appendBubble(message, "user");
          assistantBubble = appendBubble("", "assistant");
          assistantBubble.classList.add("is-streaming");
        }
        hasStarted = true;
      }

      if (eventName === "delta" && assistantBubble) {
        assistantText += payload.chunk || "";
        assistantBubble.innerHTML = renderMarkdown(assistantText);
        chatLog.scrollTop = chatLog.scrollHeight;
      } else if (eventName === "end" && assistantBubble) {
        assistantBubble.classList.remove("is-streaming");
        cityTurns.push({ role: "assistant", content: assistantText.trim() });
        saveConversationState();
      } else if (eventName === "end") {
        cityTurns.push({ role: "assistant", content: assistantText.trim() });
        saveConversationState();
      } else if (eventName === "error" && assistantBubble) {
        assistantBubble.classList.remove("is-streaming");
        throw new Error(payload.error || "Response stream failed.");
      } else if (eventName === "error") {
        throw new Error(payload.error || "Response stream failed.");
      }
    }
  }
  if (assistantBubble) {
    assistantBubble.classList.remove("is-streaming");
  }
}

function submitPrompt(promptText) {
  if (!selectedCity) {
    errorLine.textContent = "Choose a city first.";
    return;
  }
  const message = promptText.trim();
  if (!message) {
    errorLine.textContent = "Type a trip question first.";
    return;
  }

  errorLine.textContent = "";
  messageInput.value = "";
  setSubmittingState(true);

  streamAssistantReply(message)
    .catch((error) => {
      errorLine.textContent = error.message || "Something went wrong. Try again.";
    })
    .finally(() => {
      setSubmittingState(false);
    });
}

function renderStarterPrompts() {
  const promptsRoot = document.querySelector("#starter-prompts");
  if (!promptsRoot) {
    return;
  }
  promptsRoot.innerHTML = "";
  const prompts = cityOptions[selectedCity]?.starter_prompts || [];
  prompts.forEach((prompt) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "starter-chip";
    button.textContent = prompt;
    button.addEventListener("click", () => submitPrompt(prompt));
    promptsRoot.appendChild(button);
  });
}

function setActiveCity(button, options = { collapseSelector: false }) {
  cityButtons.forEach((item) => {
    const isActive = item === button;
    item.classList.toggle("is-active", isActive);
    item.setAttribute("aria-checked", isActive ? "true" : "false");
  });
  cityMenuItems.forEach((item) => {
    const isActive = item.dataset.city === button.dataset.city;
    item.classList.toggle("is-active", isActive);
  });

  selectedCity = button.dataset.city;
  activeCityLabel.textContent = button.dataset.cityLabel;
  activeCitySubtitle.textContent = button.dataset.cityCountry;
  messageInput.placeholder = button.dataset.cityHint;
  errorLine.textContent = "";
  if (options.collapseSelector) {
    planner.classList.remove("is-gated");
    planner.classList.add("is-focused");
  }
  setCityMenuOpen(false);
  renderChatForSelectedCity();
}

cityButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveCity(button, { collapseSelector: true }));
});

cityMenuItems.forEach((item) => {
  item.addEventListener("click", () => setActiveCity(item, { collapseSelector: true }));
});

if (cityButtons[0]) {
  cityConversations = loadConversationState();
  selectedCity = null;
  planner.classList.add("is-gated");
  setCityMenuOpen(false);
}

downloadPlanButton.addEventListener("click", openPlanPremiumInterstitial);
cityMenuToggle.addEventListener("click", () => {
  setCityMenuOpen(!cityMenuPanel.classList.contains("is-open"));
});
closePlanModalButton.addEventListener("click", () => setPlanModalOpen(false));
startSubscriptionButton.addEventListener("click", () => {
  setPlanModalOpen(false);
  errorLine.textContent = "Subscriptions are coming soon.";
});
planModal.addEventListener("click", (event) => {
  if (event.target.dataset.closeModal === "true") {
    setPlanModalOpen(false);
  }
});
document.addEventListener("click", (event) => {
  if (!cityMenuPanel.contains(event.target) && !cityMenuToggle.contains(event.target)) {
    setCityMenuOpen(false);
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitPrompt(messageInput.value);
});
