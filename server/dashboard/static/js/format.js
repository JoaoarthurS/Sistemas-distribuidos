/* Funções puras de formatação usadas pelo painel. */

const COLORS = ['#25d366', '#53bdeb', '#ff7eb6', '#ffb02e', '#a78bfa', '#06cf9c', '#f15c6d', '#fc9775', '#5fb8f5', '#e4a33b', '#7bc862', '#d885ff'];
const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}

export function color(name) {
  let h = 0;
  for (const ch of String(name).toLowerCase()) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}

export function initials(name) {
  const p = String(name || '?').replace(/[_.\-]+/g, ' ').trim().split(/\s+/);
  return ((p[0] || '?')[0] + (p[1] ? p[1][0] : '')).toUpperCase();
}

export function hhmmss(ts) {
  return new Date(ts).toLocaleTimeString('pt-BR');
}

export function dur(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
}

export function bytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}
