/* Cabeçalho da barra lateral: avatar, nome e selo da conexão. */
import { $ } from '../dom.js';
import { icon } from '../icons.js';
import { S } from '../store.js';
import { escapeHtml } from '../utils.js';
import { setAvatar } from './avatar.js';

export function renderMe() {
  setAvatar($('#me-avatar'), { name: S.me, kind: 'dm' });
  $('#me-name').textContent = S.me;
  const badge = $('#me-conn');
  const where = S.opts ? `${escapeHtml(S.opts.host)}:${S.opts.port}` : '';
  if (!S.connected) {
    badge.className = 'conn-badge plain';
    badge.innerHTML = `${icon('error')}<span>desconectado</span>`;
  } else if (S.secure) {
    badge.className = 'conn-badge secure';
    badge.innerHTML = `${icon('lock')}<span>${escapeHtml(S.info.tls.protocol)} · ${where}</span>`;
  } else {
    badge.className = 'conn-badge plain';
    badge.innerHTML = `${icon('unlock')}<span>sem criptografia · ${where}</span>`;
  }
  $('#empty-foot').innerHTML = S.secure
    ? `${icon('lock')} Sua conexão com o servidor é protegida por TLS`
    : `${icon('unlock')} Conexão sem criptografia (modo de referência para o Wireshark)`;
}
