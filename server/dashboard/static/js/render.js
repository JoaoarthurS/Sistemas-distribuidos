/* Renderização do painel a partir do snapshot do servidor e do feed. */
import { bytes, color, dur, esc, hhmmss, initials } from './format.js';
import { state } from './state.js';

const $ = (s) => document.querySelector(s);

const KIND_LABEL = { public: 'pública', private: 'privada', bot_request: 'pergunta', bot_response: 'resposta', bot_error: 'falha', system: 'aviso' };
const EVENT_STYLE = {
  server: ['🖥️', 'c-green'], connect: ['🔌', 'c-blue'], tls: ['🔒', 'c-green'], join: ['➕', 'c-green'],
  leave: ['➖', 'c-amber'], disconnect: ['⏏️', 'c-amber'], bot: ['🤖', 'c-violet'], timeout: ['⏱️', 'c-red'],
  error: ['⚠️', 'c-red'], warn: ['⚠️', 'c-amber'], admin: ['🛡️', 'c-blue'],
};
const THREAD_CLASSES = [['leitor', 'reader'], ['escritor', 'writer'], ['aceita', 'accept'], ['watchdog', 'watch']];

// ------------------------------------------------------------------ topo e números
function renderTop(s) {
  $('#sub').textContent = `escutando em ${s.host} · ativo há ${dur(s.uptime)} · timeout do bot ${s.request_timeout}s · inatividade ${s.idle_timeout}s`;
  const chips = [];
  if (s.tls_port) chips.push(`<span class="chip tls">🔒 TLS :${s.tls_port}</span>`);
  if (s.plain_port) chips.push(`<span class="chip plain">⚠ TCP puro :${s.plain_port}</span>`);
  chips.push(`<span class="chip dash">📊 painel :${location.port}</span>`);
  $('#top-chips').innerHTML = chips.join('');
}

function renderStats(s) {
  const named = s.clients.filter((c) => c.name);
  const humans = named.filter((c) => c.role === 'human');
  const bots = named.filter((c) => c.role === 'bot');
  const secure = named.filter((c) => c.secure).length;
  const st = s.stats;
  const cards = [
    ['👥', 'c-green', humans.length + bots.length, 'online', `${humans.length} humanos · ${bots.length} bot`],
    ['🔒', 'c-blue', `${secure}/${named.length}`, 'enlaces com TLS', `${named.length - secure} sem criptografia`],
    ['💬', 'c-violet', st.messages_public + st.messages_private, 'mensagens roteadas', `${st.messages_public} públicas · ${st.messages_private} privadas`],
    ['🤖', 'c-amber', st.bot_requests, 'perguntas ao bot', `${s.pending.length} em andamento · ${st.bot_responses} respondidas`],
    ['⏱️', 'c-red', st.bot_errors, 'falhas do bot', `${st.bot_timeouts} por tempo limite`],
    ['🧵', 'c-blue', s.threads.length, 'threads ativas', `${st.connections_total} conexões desde o início`],
  ];
  $('#stats').innerHTML = cards.map(([ico, c, v, l, sm]) =>
    `<div class="stat"><div class="ico ${c}">${ico}</div><div><b>${esc(v)}</b><span>${esc(l)}</span><small>${esc(sm)}</small></div></div>`).join('');
}

// ------------------------------------------------------------------ participantes
function clientCard(c, now) {
  const pending = !c.name;
  const name = c.name || `conexão #${c.cid}`;
  const avatar = c.role === 'bot'
    ? '<div class="avatar bot">🤖</div>'
    : `<div class="avatar" style="background:${pending ? '#667781' : color(name)}">${esc(pending ? '…' : initials(name))}</div>`;
  const role = pending ? '<span class="badge pend">handshake</span>'
    : `<span class="badge ${c.role}">${c.role === 'bot' ? 'bot' : 'humano'}</span>`;
  const link = c.secure
    ? `<div class="link on">🔒 <span><b>${esc(c.tls ? c.tls.version : 'TLS')}</b> · ${esc(c.tls ? c.tls.cipher : 'negociando…')}</span></div>`
    : '<div class="link off">⚠ <span><b>TCP sem criptografia</b> · conteúdo legível na rede</span></div>';
  return `<div class="client ${pending ? 'pending' : ''}">
    <div class="c-top">${avatar}<div><div class="c-name">${esc(name)} ${role}</div>
      <div class="c-addr">${esc(c.address)}${c.client ? ' · ' + esc(c.client) : ''}</div></div>
      ${pending ? '' : `<button class="kick" data-kick="${esc(c.name)}" title="Encerrar a conexão">Desconectar</button>`}</div>
    ${link}
    <div class="c-meta">
      <div><b>${dur((now - c.connected_at) / 1000)}</b><span>conectado</span></div>
      <div><b>${c.frames_in} / ${c.frames_out}</b><span>quadros ⬇/⬆</span></div>
      <div><b>${bytes(c.bytes_in + c.bytes_out)}</b><span>tráfego</span></div>
    </div>
    <div class="c-threads">${c.threads.map((t) => `<span class="tchip">🧵 ${esc(t)}</span>`).join('')}
      ${c.queue ? `<span class="tchip">fila: ${c.queue}</span>` : ''}</div>
  </div>`;
}

function renderClients(s) {
  $('#count-clients').textContent = s.clients.filter((c) => c.name).length;
  if (!s.clients.length) {
    $('#clients').innerHTML = '<div class="empty">Nenhum participante conectado.<br>Abra um cliente ou o bot.</div>';
    return;
  }
  const now = Date.now();
  $('#clients').innerHTML = s.clients.map((c) => clientCard(c, now)).join('');
}

// ------------------------------------------------------------------ solicitações ao bot
function renderPending(s) {
  $('#count-pending').textContent = s.pending.length;
  $('#timeout-hint').textContent = `limite ${s.request_timeout}s`;
  if (!s.pending.length) {
    $('#pending').innerHTML = '<div class="empty">Nenhuma solicitação em andamento.</div>';
    return;
  }
  $('#pending').innerHTML = s.pending.map((p) => {
    const pct = Math.min(100, (p.elapsed / s.request_timeout) * 100);
    return `<div class="req">
      <div class="req-top"><span class="rid">${esc(p.req_id)}</span><b>${esc(p.user)}</b> → ${esc(p.bot)}<span class="st">${esc(p.status)}</span></div>
      <div class="req-q" title="${esc(p.question)}">“${esc(p.question)}”</div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="req-time"><span>${p.elapsed.toFixed(1)} s</span><span>timeout em ${Math.max(0, s.request_timeout - p.elapsed).toFixed(0)} s</span></div>
    </div>`;
  }).join('');
}

// ------------------------------------------------------------------ threads
function threadClass(name) {
  const hit = THREAD_CLASSES.find(([prefix]) => name.startsWith(prefix));
  return hit ? hit[1] : '';
}

function renderThreads(s) {
  $('#count-threads').textContent = s.threads.length;
  $('#threads').innerHTML = s.threads.map((t) =>
    `<span class="thread ${threadClass(t.name)}" title="${t.daemon ? 'daemon' : 'não-daemon'}">${esc(t.name)}</span>`).join('');
}

export function renderState(s) {
  state.snap = s;
  renderTop(s);
  renderStats(s);
  renderClients(s);
  renderPending(s);
  renderThreads(s);
}

// ------------------------------------------------------------------ mensagens
function messageRow(m) {
  const sec = m.secure === true ? '<span class="sec" title="Recebida por enlace TLS">🔒</span>'
    : m.secure === false ? '<span class="sec" title="Recebida por enlace sem criptografia">⚠</span>' : '';
  const long = (m.content || '').length > 320 || (m.content || '').split('\n').length > 6;
  return `<div class="msg"><div class="time">${hhmmss(m.ts)}</div><div>
    <div class="m-head"><span class="kind ${m.kind}">${KIND_LABEL[m.kind] || m.kind}</span>
      <span class="route"><b>${esc(m.from)}</b><span class="arrow">→</span><b>${esc(m.to)}</b></span>
      ${m.req_id ? `<span class="rid">${esc(m.req_id)}</span>` : ''}${sec}</div>
    <div class="m-text ${long ? 'long' : ''}">${esc(m.content)}</div></div></div>`;
}

function matchesFilter(m) {
  const f = state.filter;
  if (f === 'public' && !(m.kind === 'public' || m.kind === 'system')) return false;
  if (f === 'private' && m.kind !== 'private') return false;
  if (f === 'bot' && !m.kind.startsWith('bot')) return false;
  if (!state.search) return true;
  const q = state.search.toLowerCase();
  return `${m.from} ${m.to} ${m.content} ${m.req_id || ''}`.toLowerCase().includes(q);
}

export function renderMessages() {
  const box = $('#messages');
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  const list = state.messages.filter(matchesFilter);
  $('#count-msgs').textContent = state.messages.length;
  box.innerHTML = list.length ? list.map(messageRow).join('')
    : '<div class="empty">Nenhuma mensagem ainda. As mensagens roteadas pelo servidor aparecem aqui.</div>';
  if (stick) box.scrollTop = box.scrollHeight;
}

// ------------------------------------------------------------------ eventos
function eventRow(e) {
  const [ico, cls] = EVENT_STYLE[e.kind] || ['•', ''];
  return `<div class="ev"><div class="ei ${cls}">${ico}</div><div class="tx">
    <span class="et">${hhmmss(e.ts)}</span><span class="th">[${esc(e.thread)}]</span><br>${esc(e.text)}</div></div>`;
}

export function renderEvents() {
  const box = $('#events');
  $('#count-events').textContent = state.events.length;
  if ($('#ev-pause').checked) return;
  box.innerHTML = state.events.map(eventRow).join('') || '<div class="empty">Sem eventos.</div>';
  box.scrollTop = box.scrollHeight;
}

// ------------------------------------------------------------------ status e avisos
export function setOnline(online) {
  $('#status').className = `status ${online ? 'on' : 'off'}`;
  $('#status-text').textContent = online ? 'servidor online' : 'sem conexão com o servidor';
}

export function toast(text) {
  const t = $('#toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 3000);
}
