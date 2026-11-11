/* Ligação dos eventos do DOM às ações da interface. */
import { bridge } from './bridge.js';
import { $ } from './dom.js';
import { expireTyping, handleFrame } from './frame-handlers.js';
import { sendText, sendTyping, stopTyping } from './messaging.js';
import { openChat } from './navigation.js';
import { doLogin, handleClosed, logout, reconnect } from './session.js';
import { S } from './store.js';
import { renderChatList } from './views/chat-list.js';
import { autoGrow, pickMention, renderMentions, setupEmojiPanel, takeInput } from './views/composer.js';
import { scrollToBottom, updateScrollButton } from './views/conversation.js';
import { closeDrawer, openDrawer, toggleDrawer } from './views/drawer.js';
import { toast, toggleTheme } from './views/feedback.js';
import { setCaPath, syncPortWithSecure } from './views/login.js';

const TYPING_SWEEP_MS = 1000;

function bindLogin() {
  $('#login-form').addEventListener('submit', doLogin);
  $('#f-secure').addEventListener('change', syncPortWithSecure);
  $('#btn-ca').addEventListener('click', async () => {
    const p = await bridge.pickCA();
    if (p) { S.caPath = p; setCaPath(p); }
  });
}

function bindSidebar() {
  $('#chat-list').addEventListener('click', (e) => {
    const li = e.target.closest('.chat-item');
    if (li) openChat(li.dataset.id);
  });
  $('#search').addEventListener('input', renderChatList);
  $('#filters').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    S.filter = chip.dataset.filter;
    document.querySelectorAll('#filters .chip').forEach((c) => c.classList.toggle('active', c === chip));
    renderChatList();
  });
  $('#btn-theme').addEventListener('click', toggleTheme);
  $('#btn-info').addEventListener('click', toggleDrawer);
  $('#btn-logout').addEventListener('click', logout);
}

function submitComposer() {
  const text = $('#input').value;
  if (!text.trim()) return;
  if (text.length > S.maxText) { toast(`A mensagem passa de ${S.maxText} caracteres.`, 'error'); return; }
  takeInput();
  stopTyping();
  sendText(text);
}

function bindComposer() {
  const ta = $('#input');
  ta.addEventListener('input', () => {
    autoGrow();
    renderMentions();
    if (ta.value.trim()) sendTyping();
    else stopTyping();
  });
  ta.addEventListener('keydown', (e) => {
    const pop = $('#mention-pop');
    if (!pop.hidden && (e.key === 'Tab' || e.key === 'Enter')) {
      const sel = pop.querySelector('.mention-item.sel');
      if (sel) { e.preventDefault(); pickMention(sel.dataset.name); return; }
    }
    if (e.key === 'Escape') { pop.hidden = true; $('#emoji-panel').hidden = true; }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitComposer(); }
  });
  $('#mention-pop').addEventListener('mousedown', (e) => {
    const it = e.target.closest('.mention-item');
    if (it) { e.preventDefault(); pickMention(it.dataset.name); }
  });
  $('#btn-send').addEventListener('click', submitComposer);
  setupEmojiPanel();
  $('#suggestions').addEventListener('click', (e) => {
    const b = e.target.closest('.suggestion');
    if (b) sendText(b.textContent);
  });
}

function retryBotQuestion(button) {
  const m = S.msgIndex.get(button.dataset.retry);
  if (!m || !m.question) return;
  const chat = S.chats.get(m.retryChat || m.chatId);
  const text = chat && chat.kind === 'bot' ? m.question : `@${m.from || 'bot'} ${m.question}`;
  sendText(text, chat ? chat.id : S.active);
}

function bindConversation() {
  $('#btn-chat-info').addEventListener('click', openDrawer);
  $('#btn-drawer-close').addEventListener('click', closeDrawer);
  $('#btn-reset').addEventListener('click', () => sendText('/reset'));
  $('#banner').addEventListener('click', (e) => {
    if (e.target.id === 'btn-reconnect') reconnect();
    if (e.target.id === 'btn-leave') logout();
  });
  $('#messages').addEventListener('click', (e) => {
    const b = e.target.closest('.retry');
    if (b) retryBotQuestion(b);
  });
  $('#messages').addEventListener('scroll', updateScrollButton);
  $('#scroll-down').addEventListener('click', () => scrollToBottom(true));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
}

export function bindEvents() {
  bindLogin();
  bindSidebar();
  bindComposer();
  bindConversation();
  setInterval(expireTyping, TYPING_SWEEP_MS);
  bridge.onFrame(handleFrame);
  bridge.onClosed(handleClosed);
}
