/* Área da conversa aberta: cabeçalho, mensagens, campo de texto e banner. */
import { BOT_SUGGESTIONS } from '../constants.js';
import { $, toElement } from '../dom.js';
import { icon } from '../icons.js';
import { activeChat, isBotStreaming, onlineHumans, pushMessage, S, userOf } from '../store.js';
import { dayKey, escapeHtml, fmtDay, modelOf, randomId } from '../utils.js';
import { setAvatar } from './avatar.js';
import { renderChatList, updateTitle } from './chat-list.js';
import { messageHtml } from './message.js';

const STICK_THRESHOLD_PX = 140;

// ------------------------------------------------------------------ cabeçalho
function statusOf(chat) {
  const typingNames = [...chat.typing.keys()];
  if (!S.connected) return { text: 'desconectado' };
  if (chat.kind === 'group') {
    if (typingNames.length) return { typing: true, text: `${typingNames.join(', ')} ${typingNames.length > 1 ? 'estão' : 'está'} digitando…` };
    const names = onlineHumans().map((u) => u.name);
    return { text: names.length ? `${names.join(', ')}, você` : 'Só você está online' };
  }
  const u = userOf(chat);
  if (!u || !u.online) return { text: 'offline' };
  if (chat.kind === 'bot') {
    if (isBotStreaming(chat)) return { typing: true, text: 'digitando…' };
    return { text: `assistente de IA · ${modelOf(u)} · respostas privadas` };
  }
  if (typingNames.length) return { typing: true, text: 'digitando…' };
  return { text: `online · ${u.secure ? 'conectado via TLS' : 'conectado sem criptografia'}` };
}

export function renderHeader() {
  const chat = activeChat();
  if (!chat) return;
  setAvatar($('#chat-avatar'), chat);
  const u = userOf(chat);
  let badge = '';
  if (chat.kind === 'bot') badge = '<span class="tag">IA</span>';
  else if (chat.kind === 'dm' && u) badge = u.secure ? icon('lock', 'lock-mini on') : icon('unlock', 'lock-mini off');
  $('#chat-name').innerHTML = `${escapeHtml(chat.name)}${badge}`;
  const st = statusOf(chat);
  const el = $('#chat-status');
  el.textContent = st.text;
  el.classList.toggle('typing', !!st.typing);
  $('#btn-reset').hidden = chat.kind !== 'bot';
}

// ------------------------------------------------------------------ campo de mensagem
function placeholderFor(chat, disabled) {
  if (!S.connected) return 'Sem conexão com o servidor';
  if (chat.kind === 'group') return 'Mensagem para todos — use @bot para perguntar ao assistente';
  if (chat.kind === 'bot') return 'Pergunte algo ao assistente…';
  return disabled ? `${chat.name} está offline` : `Mensagem para ${chat.name}`;
}

export function renderComposer() {
  const chat = activeChat();
  if (!chat) return;
  const u = userOf(chat);
  const disabled = !S.connected || (chat.kind === 'dm' && !(u && u.online));
  const input = $('#input');
  $('#composer').classList.toggle('disabled', disabled);
  input.disabled = disabled;
  input.placeholder = placeholderFor(chat, disabled);

  const sug = $('#suggestions');
  const talked = chat.messages.filter((m) => m.kind !== 'system').length;
  sug.hidden = !(chat.kind === 'bot' && talked < 2 && !disabled);
  if (!sug.hidden) sug.innerHTML = BOT_SUGGESTIONS.map((s) => `<button class="suggestion">${escapeHtml(s)}</button>`).join('');
}

// ------------------------------------------------------------------ rolagem
function nearBottom() {
  const box = $('#messages');
  return box.scrollHeight - box.scrollTop - box.clientHeight < STICK_THRESHOLD_PX;
}

export function updateScrollButton() {
  const atBottom = nearBottom();
  $('#scroll-down').hidden = atBottom;
  if (atBottom) S.newBelow = 0;
  $('#sd-badge').hidden = !S.newBelow;
  $('#sd-badge').textContent = S.newBelow;
}

export function scrollToBottom(smooth = false) {
  const box = $('#messages');
  box.scrollTo({ top: box.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  S.newBelow = 0;
  updateScrollButton();
}

// ------------------------------------------------------------------ mensagens
const daySeparator = (ts) => toElement(`<div class="day-sep">${fmtDay(ts)}</div>`);

export function renderMessages() {
  const chat = activeChat();
  const box = $('#messages');
  box.innerHTML = '';
  let prev = null;
  let lastDay = null;
  for (const m of chat.messages) {
    const dk = dayKey(m.ts);
    if (!m.header && dk !== lastDay) {
      box.appendChild(daySeparator(m.ts));
      lastDay = dk;
    }
    box.appendChild(toElement(messageHtml(m, prev)));
    prev = m;
  }
  box.dataset.lastDay = lastDay || '';
  scrollToBottom();
}

function appendMessageEl(m, prev) {
  const box = $('#messages');
  const stick = nearBottom() || m.out;
  const dk = dayKey(m.ts);
  if (!m.header && box.dataset.lastDay !== dk) {
    box.appendChild(daySeparator(m.ts));
    box.dataset.lastDay = dk;
  }
  box.appendChild(toElement(messageHtml(m, prev)));
  if (stick) scrollToBottom(true);
  else if (m.kind !== 'system') { S.newBelow += 1; updateScrollButton(); }
}

/** Re-renderiza uma mensagem já exibida (status, streaming do bot...). */
export function updateMessage(m) {
  if (S.active !== m.chatId) return;
  const chat = activeChat();
  const el = $('#messages').querySelector(`[data-id="${CSS.escape(m.id)}"]`);
  if (!el) return;
  const stick = nearBottom();
  el.replaceWith(toElement(messageHtml(m, chat.messages[chat.messages.indexOf(m) - 1])));
  if (stick) scrollToBottom();
}

/** Adiciona uma mensagem à conversa e atualiza a tela. */
export function addMessage(chatId, msg, countUnread = true) {
  const chat = S.chats.get(chatId);
  if (!chat) return null;
  const prev = chat.messages[chat.messages.length - 1];
  pushMessage(chat, msg, countUnread);
  if (S.active === chatId) appendMessageEl(msg, prev);
  renderChatList();
  updateTitle();
  return msg;
}

export function systemNote(chatId, text, variant = '') {
  addMessage(chatId, { id: 'n-' + randomId(), kind: 'system', variant, html: escapeHtml(text), ts: Date.now() }, false);
}

// ------------------------------------------------------------------ banner e presença
export function renderBanner() {
  const b = $('#banner');
  b.hidden = S.connected;
  if (S.connected) return;
  b.innerHTML = `${icon('warning')}<span class="txt"><b>Conexão com o servidor perdida.</b> ${escapeHtml(S.closeReason || '')}</span>
    <button id="btn-reconnect">Reconectar</button><button class="ghost" id="btn-leave">Sair</button>`;
}

/** Atualiza tudo que depende de quem está online/digitando. */
export function refreshPresence() {
  renderChatList();
  if (S.active) { renderHeader(); renderComposer(); }
}
