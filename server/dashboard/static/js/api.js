/* Comunicação com o servidor do painel: ações (POST JSON) e fluxo SSE. */

export async function post(url, body) {
  // JSON é exigido pelo servidor: impede que outra página dispare ações (CSRF).
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  return r.json().catch(() => ({ ok: false }));
}

export const kick = (name) => post('/api/kick', { name });
export const broadcast = (text) => post('/api/broadcast', { text });

/**
 * Abre o fluxo Server-Sent Events e repassa cada tipo de evento ao tratador
 * correspondente: { init, state, message, event, error }.
 */
export function openStream(handlers) {
  const es = new EventSource('/api/stream');
  for (const kind of ['init', 'state', 'message', 'event']) {
    if (handlers[kind]) es.addEventListener(kind, (e) => handlers[kind](JSON.parse(e.data)));
  }
  if (handlers.error) es.onerror = handlers.error;
  return es;
}
