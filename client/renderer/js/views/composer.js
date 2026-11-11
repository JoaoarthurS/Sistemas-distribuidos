/* Campo de mensagem: altura automática, contador, menções (@bot) e emojis. */
import { EMOJIS } from '../constants.js';
import { $ } from '../dom.js';
import { activeChat, S } from '../store.js';
import { escapeHtml, modelOf } from '../utils.js';
import { avatarHtml } from './avatar.js';

const MAX_INPUT_HEIGHT = 140;
const COUNTER_MARGIN = 500;   // mostra o contador quando faltam 500 caracteres

export function autoGrow() {
  const ta = $('#input');
  ta.style.height = 'auto';
  ta.style.height = `${Math.min(ta.scrollHeight, MAX_INPUT_HEIGHT)}px`;
  const n = ta.value.length;
  const cc = $('#char-count');
  cc.hidden = n < S.maxText - COUNTER_MARGIN;
  cc.textContent = `${n}/${S.maxText}`;
  cc.classList.toggle('over', n > S.maxText);
}

function mentionCandidates() {
  const chat = activeChat();
  const m = /^@([^\s]*)$/.exec($('#input').value);
  if (!chat || chat.kind === 'bot' || !m) return [];
  const q = m[1].toLowerCase();
  return [...S.users.values()].filter((u) => u.role === 'bot' && u.name.toLowerCase().startsWith(q));
}

export function renderMentions() {
  const pop = $('#mention-pop');
  const cands = mentionCandidates();
  pop.hidden = !cands.length;
  if (!cands.length) return;
  pop.innerHTML = cands.map((u, i) => `<div class="mention-item ${i === 0 ? 'sel' : ''}" data-name="${escapeHtml(u.name)}">
    ${avatarHtml(u)}<div><b>@${escapeHtml(u.name)}</b><small>${u.online ? `perguntar ao assistente (${escapeHtml(modelOf(u))})` : 'offline'}</small></div></div>`).join('');
}

export function pickMention(name) {
  const ta = $('#input');
  ta.value = `@${name} `;
  $('#mention-pop').hidden = true;
  ta.focus();
  autoGrow();
}

export function closePopups() {
  $('#mention-pop').hidden = true;
  $('#emoji-panel').hidden = true;
}

/** Esvazia o campo e devolve o texto digitado. */
export function takeInput() {
  const ta = $('#input');
  const text = ta.value;
  ta.value = '';
  autoGrow();
  closePopups();
  return text;
}

export function setupEmojiPanel() {
  const panel = $('#emoji-panel');
  const ta = $('#input');
  panel.innerHTML = EMOJIS.map((e) => `<button type="button">${e}</button>`).join('');
  $('#btn-emoji').addEventListener('click', () => { panel.hidden = !panel.hidden; });
  panel.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    const start = ta.selectionStart;
    ta.value = ta.value.slice(0, start) + b.textContent + ta.value.slice(ta.selectionEnd);
    ta.selectionStart = ta.selectionEnd = start + b.textContent.length;
    ta.focus();
    autoGrow();
  });
  document.addEventListener('click', (e) => {
    if (!panel.hidden && !e.target.closest('#emoji-panel') && !e.target.closest('#btn-emoji')) panel.hidden = true;
  });
}
