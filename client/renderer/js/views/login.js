/* Tela de login: leitura/validação do formulário e estados visuais. */
import { NAME_RE } from '../constants.js';
import { $ } from '../dom.js';
import { icon } from '../icons.js';

const fileName = (p) => String(p || '').split(/[\\/]/).pop();

export function fillLoginForm(d) {
  $('#f-name').value = d.name;
  $('#f-host').value = d.host;
  $('#f-port').value = d.port;
  $('#f-secure').checked = d.secure;
  setCaPath(d.caPath);
  updateSecureUi();
}

export function setCaPath(p) {
  $('#f-ca').textContent = fileName(p);
}

/** Lê o formulário; devolve { opts } ou { error }. */
export function readLoginForm(caPath) {
  const name = $('#f-name').value.trim();
  const host = $('#f-host').value.trim() || '127.0.0.1';
  const port = Number($('#f-port').value);
  const secure = $('#f-secure').checked;
  if (!NAME_RE.test(name)) return { error: 'Use de 2 a 20 letras, números, ".", "_" ou "-" (sem espaços).' };
  if (!(port > 0 && port < 65536)) return { error: 'Porta inválida.' };
  return { opts: { name, host, port, secure, caPath } };
}

export function showLoginError(text) {
  const el = $('#login-error');
  el.textContent = text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
  el.hidden = !text;
}

export function setLoginBusy(busy) {
  const btn = $('#btn-login');
  btn.disabled = busy;
  btn.querySelector('.spinner').hidden = !busy;
  btn.querySelector('.btn-label').textContent = busy ? 'Conectando…' : 'Entrar';
}

export function updateSecureUi() {
  const on = $('#f-secure').checked;
  const ic = $('#secure-icon');
  ic.className = `secure-icon ${on ? 'on' : 'off'}`;
  ic.innerHTML = icon(on ? 'lock' : 'unlock');
  $('#secure-title').textContent = on ? 'Conexão segura (TLS)' : 'Sem criptografia (TCP puro)';
  $('#secure-hint').textContent = on
    ? 'Certificado do servidor validado pela CA do projeto'
    : 'Só para comparação no Wireshark — o texto trafega legível';
  $('#ca-row').hidden = !on;
}

/** Troca a porta padrão junto com a chave TLS (5443 ⇄ 5000). */
export function syncPortWithSecure() {
  const port = $('#f-port');
  const secure = $('#f-secure').checked;
  if (secure && port.value === '5000') port.value = '5443';
  if (!secure && port.value === '5443') port.value = '5000';
  updateSecureUi();
}

export function showLogin(visible) {
  $('#login').hidden = !visible;
  $('#app').hidden = visible;
  if (visible) $('#f-name').focus();
}
