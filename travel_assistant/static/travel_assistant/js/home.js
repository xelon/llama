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
const subscriptionEmailInput = document.querySelector("#subscription-email");
const planModalStatus = document.querySelector("#plan-modal-status");
const cityMenuToggle = document.querySelector("#city-menu-toggle");
const cityMenuPanel = document.querySelector("#city-menu-panel");
const cityMenuItems = Array.from(document.querySelectorAll(".city-menu-item"));
const cityOptions = JSON.parse(document.querySelector("#city-options-data").textContent);
const CHAT_STORAGE_KEY = "llama_city_conversations_v1";
const SUBSCRIBER_EMAIL_STORAGE_KEY = "llama_subscriber_email_v1";
const LAST_CITY_SLUG_KEY = "llama_last_city_slug_v1";
const toastEl = document.querySelector("#toast");
const DOWNLOAD_PLAN_LABEL_DEFAULT = "Download Plan";

let selectedCity = cityButtons[0]?.dataset.city || "san-francisco";
let cityConversations = {};
let isSubmitting = false;
let isDownloadingPlan = false;

function csrfToken() {
  const input = chatForm.querySelector("input[name=csrfmiddlewaretoken]");
  return input?.value || "";
}

function appendBubble(text, who) {
  const starter = document.querySelector("#starter-state");
  if (starter) {
    starter.remove();
  }
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

function activeConversationHasContent(citySlug = selectedCity) {
  if (!citySlug) {
    return false;
  }
  const turns = getConversation(citySlug);
  return turns.some((turn) => typeof turn.content === "string" && turn.content.trim().length > 0);
}

function canDownloadPlanForActiveChat() {
  const hasVisibleChat = Boolean(chatLog.querySelector(".bubble")) && !chatLog.querySelector("#starter-state");
  return !isSubmitting && activeConversationHasContent() && hasVisibleChat;
}

function updateDownloadPlanButtonState() {
  if (isDownloadingPlan) {
    downloadPlanButton.disabled = true;
    downloadPlanButton.classList.remove("is-disabled");
    downloadPlanButton.removeAttribute("aria-disabled");
    downloadPlanButton.classList.add("is-loading");
    downloadPlanButton.textContent = "Preparing PDF…";
    downloadPlanButton.setAttribute("aria-busy", "true");
    downloadPlanButton.removeAttribute("title");
    return;
  }

  downloadPlanButton.disabled = false;
  downloadPlanButton.classList.remove("is-loading");
  downloadPlanButton.removeAttribute("aria-busy");
  const shouldDisableDownload = !canDownloadPlanForActiveChat();
  downloadPlanButton.classList.toggle("is-disabled", shouldDisableDownload);
  downloadPlanButton.setAttribute("aria-disabled", shouldDisableDownload ? "true" : "false");
  downloadPlanButton.textContent = DOWNLOAD_PLAN_LABEL_DEFAULT;
  if (shouldDisableDownload && !isSubmitting) {
    downloadPlanButton.title = "Start a chat before downloading the plan.";
  } else {
    downloadPlanButton.removeAttribute("title");
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
    updateDownloadPlanButtonState();
    return;
  }
  turns.forEach((turn) => appendBubble(turn.content, turn.role));
  updateDownloadPlanButtonState();
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

function setPlanModalStatus(message, hasError = false) {
  if (!planModalStatus) {
    return;
  }
  planModalStatus.textContent = message || "";
  planModalStatus.classList.toggle("is-error", hasError);
}

function getStoredSubscriberEmail() {
  try {
    return localStorage.getItem(SUBSCRIBER_EMAIL_STORAGE_KEY) || "";
  } catch (_error) {
    return "";
  }
}

function setStoredSubscriberEmail(email) {
  try {
    localStorage.setItem(SUBSCRIBER_EMAIL_STORAGE_KEY, email);
  } catch (_error) {
    // Ignore storage errors.
  }
}

function saveLastSelectedCity(slug) {
  const city = slug || selectedCity;
  if (!city || !cityOptions[city]) {
    return;
  }
  try {
    localStorage.setItem(LAST_CITY_SLUG_KEY, city);
  } catch (_error) {
    // Ignore storage errors.
  }
}

function showToast(message) {
  if (!toastEl || !message) {
    return;
  }
  toastEl.textContent = message;
  toastEl.hidden = false;
  toastEl.classList.add("is-visible");
  clearTimeout(showToast._hideTimer);
  showToast._hideTimer = window.setTimeout(() => {
    toastEl.classList.remove("is-visible");
    toastEl.hidden = true;
  }, 4200);
}

function hasBillingPlannerReturnParams() {
  const params = new URLSearchParams(window.location.search);
  return Boolean(
    params.get("subscription") ||
      params.get("checkout") ||
      params.get("billing") === "return",
  );
}

function stripBillingReturnQueryParamsFromUrl() {
  const url = new URL(window.location.href);
  let changed = false;
  ["subscription", "checkout"].forEach((key) => {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  });
  if (url.searchParams.get("billing") === "return") {
    url.searchParams.delete("billing");
    changed = true;
  }
  if (!changed) {
    return;
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState({}, "", next);
}

function restorePlannerAfterBillingReturn() {
  if (!hasBillingPlannerReturnParams()) {
    return;
  }
  let slug = "";
  try {
    slug = localStorage.getItem(LAST_CITY_SLUG_KEY) || "";
  } catch (_error) {
    return;
  }
  if (!slug || !cityOptions[slug]) {
    return;
  }
  const pill = cityButtons.find((b) => b.dataset.city === slug);
  const item = cityMenuItems.find((b) => b.dataset.city === slug);
  const btn = pill || item;
  if (btn) {
    setActiveCity(btn, { collapseSelector: true });
  }
}

function applyBillingReturnFeedback() {
  if (!hasBillingPlannerReturnParams()) {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const subscription = (params.get("subscription") || "").toLowerCase();
  const checkout = (params.get("checkout") || "").toLowerCase();
  let toastMessage = "";

  if (subscription === "success") {
    toastMessage = "Subscription is active.";
  } else if (subscription === "processing") {
    toastMessage = "Subscription is processing. Try downloading again in a few seconds.";
  } else if (subscription === "failed") {
    toastMessage = "We could not verify the subscription. Please try again.";
  } else if (checkout === "cancelled") {
    toastMessage = "Checkout was cancelled.";
  } else if (checkout === "success") {
    toastMessage = "Subscription is active.";
  } else if (checkout === "processing") {
    toastMessage = "Subscription is processing. Try downloading again in a few seconds.";
  } else if (checkout === "failed") {
    toastMessage = "We could not verify the subscription. Please try again.";
  }

  if (toastMessage) {
    showToast(toastMessage);
  }
  stripBillingReturnQueryParamsFromUrl();
}

function getDownloadPayload() {
  return {
    city: selectedCity,
    conversationTurns: getConversation(selectedCity),
    subscriberEmail: (subscriptionEmailInput?.value || "").trim().toLowerCase(),
  };
}

async function requestPlanPdfDownload() {
  const response = await fetch("/api/plan/pdf/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(getDownloadPayload()),
  });
  if (!response.ok) {
    let errorMessage = "Could not download plan right now.";
    try {
      const payload = await response.json();
      if (payload.error) {
        errorMessage = payload.error;
      }
    } catch (_error) {
      // Keep fallback message.
    }
    const statusError = new Error(errorMessage);
    statusError.status = response.status;
    throw statusError;
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  const safeCity = (selectedCity || "trip").replace(/[^a-z-]/g, "");
  anchor.download = `llama-plan-${safeCity}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

async function startSubscriptionCheckout() {
  const email = (subscriptionEmailInput?.value || "").trim().toLowerCase();
  if (!email || !email.includes("@")) {
    setPlanModalStatus("Enter a valid email to continue to checkout.", true);
    return;
  }
  setPlanModalStatus("Checking subscription access...");
  setStoredSubscriberEmail(email);
  startSubscriptionButton.disabled = true;
  try {
    const restoreResponse = await fetch("/api/billing/request-restore-link/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({ email }),
    });
    const restorePayload = await restoreResponse.json();
    if (!restoreResponse.ok) {
      throw new Error(restorePayload.error || "Could not check restore access right now.");
    }
    if (restorePayload.action === "restore_sent") {
      setPlanModalStatus("We emailed you a secure magic link to restore access on this browser.");
      return;
    }
    if (restorePayload.action !== "checkout_required") {
      throw new Error("Unexpected restore response.");
    }

    setPlanModalStatus("Preparing secure checkout...");
    const response = await fetch("/api/billing/create-checkout-session/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        city: selectedCity,
        conversationTurns: getConversation(selectedCity),
        email,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.checkoutUrl) {
      throw new Error(payload.error || "Could not start checkout right now.");
    }
    saveLastSelectedCity(selectedCity);
    window.location.href = payload.checkoutUrl;
  } catch (error) {
    setPlanModalStatus(error.message || "Could not start checkout right now.", true);
  } finally {
    startSubscriptionButton.disabled = false;
  }
}

function setCityMenuOpen(isOpen) {
  cityMenuPanel.classList.toggle("is-open", isOpen);
  cityMenuPanel.setAttribute("aria-hidden", isOpen ? "false" : "true");
  cityMenuToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
}

function setSubmittingState(submitting) {
  isSubmitting = submitting;
  sendButton.disabled = submitting;
  sendButton.classList.toggle("is-loading", submitting);
  sendButton.textContent = submitting ? "Writing..." : "Ask";
  updateDownloadPlanButtonState();
  cityMenuToggle.disabled = submitting;
  cityButtons.forEach((button) => {
    button.disabled = submitting;
  });
  cityMenuItems.forEach((item) => {
    item.disabled = submitting;
  });
}

function openPlanPremiumInterstitial() {
  if (!canDownloadPlanForActiveChat()) {
    updateDownloadPlanButtonState();
    return;
  }
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
    let backendError = "";
    try {
      const text = await response.text();
      if (text) {
        try {
          const payload = JSON.parse(text);
          backendError = payload.error || "";
        } catch (_jsonError) {
          backendError = text.slice(0, 180);
        }
      }
    } catch (_readError) {
      // Ignore response parsing issues and keep fallback.
    }
    throw new Error(backendError || "Assistant unavailable right now. Try again.");
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
  saveLastSelectedCity(button.dataset.city);
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
  restorePlannerAfterBillingReturn();
}

if (subscriptionEmailInput) {
  subscriptionEmailInput.value = getStoredSubscriberEmail();
}
applyBillingReturnFeedback();

updateDownloadPlanButtonState();

downloadPlanButton.addEventListener("click", async () => {
  if (isDownloadingPlan || !canDownloadPlanForActiveChat()) {
    updateDownloadPlanButtonState();
    return;
  }
  errorLine.textContent = "";
  isDownloadingPlan = true;
  updateDownloadPlanButtonState();
  try {
    await requestPlanPdfDownload();
  } catch (error) {
    if (error.status === 403) {
      setPlanModalStatus("Subscription required before download.");
      openPlanPremiumInterstitial();
      return;
    }
    errorLine.textContent = error.message || "Could not download plan right now.";
  } finally {
    isDownloadingPlan = false;
    updateDownloadPlanButtonState();
  }
});
cityMenuToggle.addEventListener("click", () => {
  setCityMenuOpen(!cityMenuPanel.classList.contains("is-open"));
});
closePlanModalButton.addEventListener("click", () => {
  setPlanModalOpen(false);
  setPlanModalStatus("");
});
startSubscriptionButton.addEventListener("click", startSubscriptionCheckout);
planModal.addEventListener("click", (event) => {
  if (event.target.dataset.closeModal === "true") {
    setPlanModalOpen(false);
    setPlanModalStatus("");
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
