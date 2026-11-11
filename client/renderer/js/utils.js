/* Funções puras (sem DOM nem estado): texto, cores, datas e identificadores. */

const COLORS = ['#25d366', '#53bdeb', '#ff7eb6', '#ffb02e', '#a78bfa', '#06cf9c', '#f15c6d', '#fc9775', '#5fb8f5', '#e4a33b', '#7bc862', '#d885ff'];
const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}

/** Chave sem distinção de maiúsculas (nomes são únicos ignorando caixa). */
export const key = (name) => String(name || '').toLowerCase();
export const chatIdFor = (name) => 'u:' + key(name);

export function hashColor(name) {
  let h = 0;
  for (const ch of key(name)) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}

export function initials(name) {
  const parts = String(name).replace(/[_.\-]+/g, ' ').trim().split(/\s+/);
  return ((parts[0] || '?')[0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
}

export const fmtTime = (ts) => new Date(ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

export function dayKey(ts) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

export function fmtDay(ts) {
  if (dayKey(ts) === dayKey(Date.now())) return 'Hoje';
  if (dayKey(ts) === dayKey(Date.now() - 864e5)) return 'Ontem';
  return new Date(ts).toLocaleDateString('pt-BR');
}

export function randomId() {
  const a = new Uint8Array(6);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(2)} MB`;
}

/** Modelo da LLM anunciado pelo bot no HELLO (client = "sd-bot/<modelo>"). */
export function modelOf(user) {
  const m = /sd-bot\/(.+)$/.exec((user && user.client) || '');
  return m ? m[1] : 'LLM local';
}
