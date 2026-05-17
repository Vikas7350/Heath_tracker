/**
 * AI Chatbot — handles message sending, history, typing indicator
 */

let chatHistory = [];

const chatWindow  = document.getElementById('chat-window');
const userInput   = document.getElementById('user-input');
const sendBtn     = document.getElementById('send-btn');

// ── Keyboard shortcut: Ctrl+Enter to send ───────────────────────────────────
userInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ── Send suggestion chip ─────────────────────────────────────────────────────
function sendSuggestion(el) {
  userInput.value = el.textContent;
  sendMessage();
}

// ── Main send function ───────────────────────────────────────────────────────
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text) return;

  // Append user bubble
  appendMessage('user', text);
  chatHistory.push({ role: 'user', content: text });
  userInput.value = '';
  sendBtn.disabled = true;

  // Show typing indicator
  const typingId = showTyping();

  try {
    const res = await fetch('/chat', {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
      },
      body:    JSON.stringify({ message: text, history: chatHistory }),
    });
    const data = await res.json();
    removeTyping(typingId);

    const reply = data.reply || 'Sorry, I could not get a response. Please try again.';
    appendMessage('bot', reply);
    chatHistory.push({ role: 'assistant', content: reply });

    // Keep history to last 20 messages to avoid too-large payloads
    if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);

  } catch (err) {
    removeTyping(typingId);
    appendMessage('bot', '⚠️ Connection error. Please check your internet and try again.');
  }

  sendBtn.disabled = false;
  userInput.focus();
}

// ── DOM helpers ──────────────────────────────────────────────────────────────
function appendMessage(role, text) {
  const div = document.createElement('div');
  div.className = `chat-message ${role}`;

  const icon = role === 'bot'
    ? '<i class="bi bi-robot"></i>'
    : '<i class="bi bi-person-fill"></i>';

  // Convert newlines and basic markdown bold **text** → <strong>
  const formatted = text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

  div.innerHTML = `
    <div class="avatar">${icon}</div>
    <div class="bubble">${formatted}</div>
  `;

  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div;
}

function showTyping() {
  const id  = 'typing-' + Date.now();
  const div = document.createElement('div');
  div.className = 'chat-message bot typing';
  div.id        = id;
  div.innerHTML = `
    <div class="avatar"><i class="bi bi-robot"></i></div>
    <div class="bubble">
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>
    </div>
  `;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}
