/* Notificações rápidas (toasts) e tema claro/escuro. */
import { TOAST_MS } from '../constants.js';
import { $, toElement } from '../dom.js';
import { icon } from '../icons.js';
import { escapeHtml } from '../utils.js';

const TOAST_ICONS = { error: 'error', ok: 'ok', info: 'info' };
const THEME_KEY = 'sdchat-theme';

export function toast(text, kind = 'info') {
  const el = toElement(`<div class="toast ${kind}">${icon(TOAST_ICONS[kind] || 'info')}<span>${escapeHtml(text)}</span></div>`);
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), TOAST_MS);
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('#btn-theme').innerHTML = icon(theme === 'dark' ? 'sun' : 'moon');
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* armazenamento indisponível */ }
}

export function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

/** --theme=light|dark força o tema; senão, o último usado ou o do sistema. */
export function initialTheme(forced) {
  if (forced === 'light' || forced === 'dark') return forced;
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) return saved;
  } catch { /* ignorado */ }
  return matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}
