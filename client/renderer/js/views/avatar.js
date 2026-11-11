/* Avatares: grupo, bot ou iniciais coloridas. */
import { icon } from '../icons.js';
import { escapeHtml, hashColor, initials } from '../utils.js';

export function avatarHtml(chatOrUser, presence = false) {
  const kind = chatOrUser.kind || (chatOrUser.role === 'bot' ? 'bot' : 'dm');
  const dot = presence ? '<span class="presence"></span>' : '';
  if (kind === 'group') return `<div class="avatar group">${icon('group')}</div>`;
  if (kind === 'bot') return `<div class="avatar bot">${icon('robot')}${dot}</div>`;
  const name = chatOrUser.name;
  return `<div class="avatar" style="background:${hashColor(name)}">${escapeHtml(initials(name))}${dot}</div>`;
}

/** Atualiza um elemento .avatar existente (cabeçalhos). */
export function setAvatar(el, chatOrUser) {
  const tmp = document.createElement('div');
  tmp.innerHTML = avatarHtml(chatOrUser);
  const src = tmp.firstElementChild;
  el.className = src.className;
  el.style.background = src.style.background;
  el.innerHTML = src.innerHTML;
}
