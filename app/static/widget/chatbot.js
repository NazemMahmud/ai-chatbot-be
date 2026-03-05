/**
 * AI Chatbot Widget - Embeddable chat widget
 *
 * Usage:
 *   <script src="https://your-api.com/widget/chatbot.js"
 *     data-bot-id="uuid"
 *     data-position="bottom-right"
 *     data-theme="light"
 *     data-api-url="https://your-api.com"
 *     async></script>
 */
(function () {
  "use strict";

  // ---- Config from script tag ----
  const scriptTag = document.currentScript;
  if (!scriptTag) return;

  const BOT_ID = scriptTag.getAttribute("data-bot-id");
  if (!BOT_ID) {
    console.error("[Chatbot] data-bot-id is required");
    return;
  }

  const POSITION = scriptTag.getAttribute("data-position") || "bottom-right";
  const THEME = scriptTag.getAttribute("data-theme") || "light";
  const API_URL = scriptTag.getAttribute("data-api-url") || scriptTag.src.replace(/\/widget\/chatbot\.js.*/, "");

  const SESSION_KEY = `chatbot_session_${BOT_ID}`;
  let sessionId = localStorage.getItem(SESSION_KEY) || null;
  let isOpen = false;
  let isLoading = false;

  // ---- Theme colors ----
  const themes = {
    light: {
      bg: "#ffffff",
      text: "#1f2937",
      input_bg: "#f3f4f6",
      bubble_bg: "#f3f4f6",
      user_bg: "#6366f1",
      user_text: "#ffffff",
      border: "#e5e7eb",
    },
    dark: {
      bg: "#1f2937",
      text: "#f9fafb",
      input_bg: "#374151",
      bubble_bg: "#374151",
      user_bg: "#6366f1",
      user_text: "#ffffff",
      border: "#4b5563",
    },
  };
  const t = themes[THEME] || themes.light;

  // ---- Styles ----
  const style = document.createElement("style");
  style.textContent = `
    #cb-widget-container * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    #cb-bubble {
      position: fixed; ${POSITION === "bottom-left" ? "left: 20px" : "right: 20px"}; bottom: 20px;
      width: 56px; height: 56px; border-radius: 50%;
      background: #6366f1; color: white; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 99998;
      transition: transform 0.2s;
    }
    #cb-bubble:hover { transform: scale(1.1); }
    #cb-bubble svg { width: 24px; height: 24px; fill: currentColor; }
    #cb-panel {
      position: fixed; ${POSITION === "bottom-left" ? "left: 20px" : "right: 20px"}; bottom: 90px;
      width: 380px; max-width: calc(100vw - 40px); height: 520px; max-height: calc(100vh - 120px);
      background: ${t.bg}; border-radius: 12px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.12);
      display: none; flex-direction: column; z-index: 99999;
      border: 1px solid ${t.border}; overflow: hidden;
    }
    #cb-panel.open { display: flex; }
    #cb-header {
      padding: 16px; background: #6366f1; color: white;
      display: flex; align-items: center; justify-content: space-between;
      flex-shrink: 0;
    }
    #cb-header h3 { font-size: 15px; font-weight: 600; }
    #cb-close { background: none; border: none; color: white; cursor: pointer; font-size: 20px; padding: 4px; }
    #cb-messages {
      flex: 1; overflow-y: auto; padding: 16px;
      display: flex; flex-direction: column; gap: 10px;
    }
    .cb-msg {
      max-width: 85%; padding: 10px 14px; border-radius: 12px;
      font-size: 14px; line-height: 1.5; word-wrap: break-word;
    }
    .cb-msg.assistant { background: ${t.bubble_bg}; color: ${t.text}; align-self: flex-start; border-bottom-left-radius: 4px; }
    .cb-msg.user { background: ${t.user_bg}; color: ${t.user_text}; align-self: flex-end; border-bottom-right-radius: 4px; }
    .cb-typing { display: flex; gap: 4px; padding: 10px 14px; align-self: flex-start; }
    .cb-typing span { width: 8px; height: 8px; border-radius: 50%; background: #9ca3af; animation: cb-bounce 1.4s infinite; }
    .cb-typing span:nth-child(2) { animation-delay: 0.2s; }
    .cb-typing span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes cb-bounce { 0%,80%,100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
    #cb-input-area {
      display: flex; padding: 12px; border-top: 1px solid ${t.border};
      background: ${t.bg}; flex-shrink: 0; gap: 8px;
    }
    #cb-input {
      flex: 1; padding: 10px 14px; border: 1px solid ${t.border};
      border-radius: 8px; font-size: 14px; outline: none;
      background: ${t.input_bg}; color: ${t.text}; resize: none;
    }
    #cb-input:focus { border-color: #6366f1; }
    #cb-send {
      background: #6366f1; color: white; border: none; border-radius: 8px;
      padding: 10px 14px; cursor: pointer; font-size: 14px; flex-shrink: 0;
    }
    #cb-send:disabled { opacity: 0.5; cursor: not-allowed; }
    @media (max-width: 480px) {
      #cb-panel { width: 100vw; height: 100vh; max-height: 100vh; bottom: 0; left: 0; right: 0; border-radius: 0; }
      #cb-bubble { bottom: 16px; right: 16px; }
    }
  `;
  document.head.appendChild(style);

  // ---- DOM ----
  const container = document.createElement("div");
  container.id = "cb-widget-container";

  container.innerHTML = `
    <button id="cb-bubble" aria-label="Open chat">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
    </button>
    <div id="cb-panel">
      <div id="cb-header">
        <h3 id="cb-title">Chat</h3>
        <button id="cb-close">&times;</button>
      </div>
      <div id="cb-messages"></div>
      <div id="cb-input-area">
        <input id="cb-input" type="text" placeholder="Type a message..." autocomplete="off" />
        <button id="cb-send">Send</button>
      </div>
    </div>
  `;
  document.body.appendChild(container);

  const bubble = document.getElementById("cb-bubble");
  const panel = document.getElementById("cb-panel");
  const closeBtn = document.getElementById("cb-close");
  const messagesEl = document.getElementById("cb-messages");
  const inputEl = document.getElementById("cb-input");
  const sendBtn = document.getElementById("cb-send");
  const titleEl = document.getElementById("cb-title");

  // ---- Functions ----
  function toggleChat() {
    isOpen = !isOpen;
    panel.classList.toggle("open", isOpen);
    if (isOpen) {
      inputEl.focus();
      if (messagesEl.children.length === 0) {
        loadConfig();
      }
    }
  }

  function addMessage(role, text) {
    const div = document.createElement("div");
    div.className = `cb-msg ${role}`;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function showTyping() {
    const div = document.createElement("div");
    div.className = "cb-typing";
    div.id = "cb-typing-indicator";
    div.innerHTML = "<span></span><span></span><span></span>";
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideTyping() {
    const el = document.getElementById("cb-typing-indicator");
    if (el) el.remove();
  }

  async function loadConfig() {
    try {
      const res = await fetch(`${API_URL}/api/widget/config/${BOT_ID}`);
      const json = await res.json();
      if (json.success && json.data) {
        titleEl.textContent = json.data.bot_name || "Chat";
        if (json.data.welcome_message) {
          addMessage("assistant", json.data.welcome_message);
        }
        // Apply custom color if provided
        const cfg = json.data.widget_config || {};
        if (cfg.primary_color) {
          bubble.style.background = cfg.primary_color;
          document.getElementById("cb-header").style.background = cfg.primary_color;
          sendBtn.style.background = cfg.primary_color;
        }
      }
    } catch (e) {
      console.error("[Chatbot] Failed to load config:", e);
    }

    // Load history if session exists
    if (sessionId) {
      try {
        const res = await fetch(`${API_URL}/api/widget/history/${BOT_ID}/${sessionId}`);
        const json = await res.json();
        if (json.success && Array.isArray(json.data)) {
          json.data.forEach(function (msg) {
            addMessage(msg.role, msg.content);
          });
        }
      } catch (e) {
        // Ignore history load errors
      }
    }
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isLoading) return;

    addMessage("user", text);
    inputEl.value = "";
    isLoading = true;
    sendBtn.disabled = true;
    showTyping();

    try {
      const res = await fetch(`${API_URL}/api/widget/chat/${BOT_ID}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const json = await res.json();

      hideTyping();

      if (json.success && json.data) {
        addMessage("assistant", json.data.message);
        if (json.data.session_id) {
          sessionId = json.data.session_id;
          localStorage.setItem(SESSION_KEY, sessionId);
        }
      } else {
        addMessage("assistant", json.message || "Sorry, something went wrong.");
      }
    } catch (e) {
      hideTyping();
      addMessage("assistant", "Sorry, I could not connect to the server.");
    }

    isLoading = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }

  // ---- Events ----
  bubble.addEventListener("click", toggleChat);
  closeBtn.addEventListener("click", toggleChat);
  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
})();
