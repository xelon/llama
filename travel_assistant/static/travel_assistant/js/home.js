const cityButtons = Array.from(document.querySelectorAll(".city-pill"));
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
const planPreviewContent = document.querySelector("#plan-preview-content");
const planModalError = document.querySelector("#plan-modal-error");
const closePlanModalButton = document.querySelector("#close-plan-modal");
const savePlanPdfButton = document.querySelector("#save-plan-pdf");
const cityOptions = JSON.parse(document.querySelector("#city-options-data").textContent);

let selectedCity = cityButtons[0]?.dataset.city || "san-francisco";
const conversationTurns = [];

function csrfToken() {
  const input = chatForm.querySelector("input[name=csrfmiddlewaretoken]");
  return input?.value || "";
}

function appendBubble(text, who) {
  if (starterState) {
    starterState.remove();
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

function setSubmittingState(isSubmitting) {
  sendButton.disabled = isSubmitting;
  sendButton.classList.toggle("is-loading", isSubmitting);
  sendButton.textContent = isSubmitting ? "Writing..." : "Ask";
  downloadPlanButton.disabled = isSubmitting;
}

function renderSummaryPreview(summary) {
  const renderList = (title, items) => `
    <section class="preview-block">
      <h4>${title}</h4>
      <ul>${(items || []).map((item) => `<li>${item}</li>`).join("") || "<li>No items.</li>"}</ul>
    </section>
  `;

  const dayBlocks = (summary.day_plan || []).map((day) => {
    const items = (day.items || []).map((item) => `<li>${item}</li>`).join("");
    return `<section class="preview-block"><h4>${day.day || "Day"}</h4><ul>${items || "<li>No items.</li>"}</ul></section>`;
  }).join("");

  planPreviewContent.innerHTML = `
    <h3 class="preview-title">${summary.title || "Trip Plan"}</h3>
    ${renderList("Overview", summary.trip_overview)}
    ${dayBlocks || renderList("Day Plan", [])}
    ${renderList("Logistics", summary.logistics)}
    ${renderList("Reservations", summary.reservations)}
    ${renderList("Alternatives", summary.alternatives)}
    ${renderList("Notes", summary.notes)}
  `;
}

async function openPlanPreview() {
  if (!conversationTurns.length) {
    errorLine.textContent = "Start a conversation before downloading.";
    return;
  }

  planModalError.textContent = "";
  planPreviewContent.innerHTML = "<p>Preparing preview...</p>";
  setPlanModalOpen(true);

  try {
    const response = await fetch("/api/plan/preview/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        city: selectedCity,
        conversationTurns,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not generate preview.");
    }
    renderSummaryPreview(payload.summary);
  } catch (error) {
    planPreviewContent.innerHTML = "";
    planModalError.textContent = error.message || "Could not generate preview.";
  }
}

async function savePlanPdf() {
  planModalError.textContent = "";
  savePlanPdfButton.disabled = true;
  savePlanPdfButton.classList.add("is-loading");
  savePlanPdfButton.textContent = "Saving...";

  try {
    const response = await fetch("/api/plan/pdf/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        city: selectedCity,
        conversationTurns,
      }),
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error || "Could not generate PDF.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `llama-plan-${selectedCity}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    planModalError.textContent = error.message || "Could not generate PDF.";
  } finally {
    savePlanPdfButton.disabled = false;
    savePlanPdfButton.classList.remove("is-loading");
    savePlanPdfButton.textContent = "Save PDF";
  }
}

async function streamAssistantReply(message) {
  const response = await fetch("/api/chat/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify({
      city: selectedCity,
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
        appendBubble(message, "user");
        conversationTurns.push({ role: "user", content: message });
        assistantBubble = appendBubble("", "assistant");
        assistantBubble.classList.add("is-streaming");
        hasStarted = true;
      }

      if (eventName === "delta" && assistantBubble) {
        assistantText += payload.chunk || "";
        assistantBubble.innerHTML = renderMarkdown(assistantText);
        chatLog.scrollTop = chatLog.scrollHeight;
      } else if (eventName === "end" && assistantBubble) {
        assistantBubble.classList.remove("is-streaming");
        conversationTurns.push({ role: "assistant", content: assistantText.trim() });
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
  if (!starterPrompts) {
    return;
  }
  starterPrompts.innerHTML = "";
  const prompts = cityOptions[selectedCity]?.starter_prompts || [];
  prompts.forEach((prompt) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "starter-chip";
    button.textContent = prompt;
    button.addEventListener("click", () => submitPrompt(prompt));
    starterPrompts.appendChild(button);
  });
}

function setActiveCity(button) {
  cityButtons.forEach((item) => {
    const isActive = item === button;
    item.classList.toggle("is-active", isActive);
    item.setAttribute("aria-checked", isActive ? "true" : "false");
  });

  selectedCity = button.dataset.city;
  activeCityLabel.textContent = button.dataset.cityLabel;
  activeCitySubtitle.textContent = button.dataset.cityCountry;
  messageInput.placeholder = button.dataset.cityHint;
  errorLine.textContent = "";
  renderStarterPrompts();
}

cityButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveCity(button));
});

if (cityButtons[0]) {
  setActiveCity(cityButtons[0]);
}

downloadPlanButton.addEventListener("click", openPlanPreview);
closePlanModalButton.addEventListener("click", () => setPlanModalOpen(false));
savePlanPdfButton.addEventListener("click", savePlanPdf);
planModal.addEventListener("click", (event) => {
  if (event.target.dataset.closeModal === "true") {
    setPlanModalOpen(false);
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitPrompt(messageInput.value);
});
