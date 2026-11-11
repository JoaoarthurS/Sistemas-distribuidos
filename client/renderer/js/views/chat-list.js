/* Barra lateral: lista de conversas e título da janela. */
import { $ } from '../dom.js';
import { icon } from '../icons.js';
import { isBotStreaming, lastRealMessage, S, userOf } from '../store.js';
import { escapeHtml, fmtTime } from '../utils.js';
import { avatarHtml } from './avatar.js';
import { tickHtml } from './message.js';

const FILTERS = {
  all: () => true,
  unread: (c) => c.unread > 0,
  online: (c) => c.kind === 'group' || !!(userOf(c) && userOf(c).online),
};

function emptyPreview(chat) {
  if (chat.kind === 'group') return 'Todos os participantes conectados';
  if (chat.kind === 'bot') return 'Pergunte qualquer coisa ao assistente';
  return userOf(chat) && userOf(chat).online ? 'online' : 'offline';
}

/** Texto curto abaixo do nome: "digitando…", última mensagem ou um padrão. */
function previewOf(chat) {
  const typingNames = [...chat.typing.keys()];
  if (chat.kind === 'group' && typingNames.length) return { typing: true, html: `${escapeHtml(typingNames[0])} está digitando…` };
  if (chat.kind !== 'group' && (typingNames.length || isBotStreaming(chat))) return { typing: true, html: 'digitando…' };
  const last = lastRealMessage(chat);
  if (!last) return { html: emptyPreview(chat) };
  let prefix = '';
  if (last.out) prefix = tickHtml(last, 'xs');
  else if (chat.kind === 'group' && last.from) prefix = `<span class="sender">${escapeHtml(last.from)}: </span>`;
  let body = last.kind === 'bot-error' ? `⚠ ${last.text}` : last.text || '';
  if (last.kind === 'bot' && !body) body = 'digitando…';
  return { html: prefix + escapeHtml(body.replace(/[*_`#>|~]/g, '').replace(/\s+/g, ' ').slice(0, 90)) };
}

function badgeFor(chat, user) {
  if (chat.kind === 'bot') return '<span class="tag">IA</span>';
  if (chat.kind !== 'dm' || !user) return '';
  return user.secure
    ? `<span title="Conectado via TLS">${icon('lock', 'lock-mini on')}</span>`
    : `<span title="Conectado sem criptografia">${icon('unlock', 'lock-mini off')}</span>`;
}

function chatItemHtml(c) {
  const u = userOf(c);
  const online = c.kind !== 'group' && !!(u && u.online);
  const p = previewOf(c);
  const last = lastRealMessage(c);
  return `<li class="chat-item ${c.id === S.active ? 'active' : ''}" data-id="${escapeHtml(c.id)}">
    ${avatarHtml(c, online)}
    <div class="ci-body">
      <div class="ci-top"><span class="ci-name"><span class="nm">${escapeHtml(c.name)}</span>${badgeFor(c, u)}</span>
        <span class="ci-time ${c.unread ? 'unread' : ''}">${last ? fmtTime(last.ts) : ''}</span></div>
      <div class="ci-bottom"><span class="ci-preview ${p.typing ? 'typing' : ''}">${p.html}</span>
        ${c.unread ? `<span class="badge">${c.unread}</span>` : ''}</div>
    </div></li>`;
}

export function renderChatList() {
  const list = $('#chat-list');
  const q = $('#search').value.trim().toLowerCase();
  const chats = [...S.chats.values()]
    .filter((c) => !q || c.name.toLowerCase().includes(q))
    .filter(FILTERS[S.filter] || FILTERS.all)
    .sort((a, b) => b.lastTs - a.lastTs);
  list.innerHTML = chats.length
    ? chats.map(chatItemHtml).join('')
    : `<li class="empty-list">${q ? 'Nenhuma conversa encontrada.' : 'Nada por aqui.'}</li>`;
}

export function updateTitle() {
  const unread = [...S.chats.values()].reduce((n, c) => n + c.unread, 0);
  document.title = `${unread ? `(${unread}) ` : ''}SD Chat${S.me ? ` — ${S.me}` : ''}`;
}
