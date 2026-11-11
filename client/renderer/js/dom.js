/* Atalhos de DOM. */

export const $ = (sel) => document.querySelector(sel);

export function toElement(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
