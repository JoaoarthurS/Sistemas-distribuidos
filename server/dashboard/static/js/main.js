/* Painel do servidor: liga o fluxo SSE (/api/stream) à renderização e às ações. */
import { broadcast, kick, openStream } from './api.js';
import { renderEvents, renderMessages, renderState, setOnline, toast } from './render.js';
import { addEvent, addMessage, resetFeed, state } from './state.js';
import { applyTheme, initialTheme, toggleTheme } from './theme.js';

const $ = (s) => document.querySelector(s);

function connect() {
  openStream({
    init(d) {
      resetFeed(d);
      renderState(d);
      renderMessages();
      renderEvents();
      setOnline(true);
    },
    state: renderState,
    message(m) { addMessage(m); renderMessages(); },
    event(e) { addEvent(e); renderEvents(); },
    error() { setOnline(false); },
  });
}

function bindActions() {
  $('#clients').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-kick]');
    if (!b) return;
    const name = b.dataset.kick;
    if (!confirm(`Desconectar ${name}?`)) return;
    const r = await kick(name);
    toast(r.ok ? `${name} foi desconectado.` : `Não foi possível desconectar ${name}.`);
  });

  $('#broadcast').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#broadcast-text');
    const text = input.value.trim();
    if (!text) return;
    const r = await broadcast(text);
    if (r.ok) { input.value = ''; toast(`Aviso enviado a ${r.recipients} participante(s).`); }
    else toast(r.error || 'Falha ao enviar aviso.');
  });

  $('#msg-tabs').addEventListener('click', (e) => {
    const t = e.target.closest('.tab');
    if (!t) return;
    state.filter = t.dataset.f;
    document.querySelectorAll('#msg-tabs .tab').forEach((x) => x.classList.toggle('active', x === t));
    renderMessages();
  });
  $('#msg-search').addEventListener('input', (e) => { state.search = e.target.value.trim(); renderMessages(); });
  $('#ev-pause').addEventListener('change', renderEvents);
  $('#theme').addEventListener('click', toggleTheme);
}

applyTheme(initialTheme());
bindActions();
connect();
