/* Marcação HTML de uma mensagem (bolhas, ticks, respostas do bot). */
import { formatWhats, renderMarkdown } from '../format.js';
import { icon } from '../icons.js';
import { S } from '../store.js';
import { escapeHtml, fmtTime, hashColor } from '../utils.js';

const GROUPING_MS = 5 * 60e3;

/** Primeira de uma sequência do mesmo remetente (mostra o "rabinho" da bolha). */
function isFirst(msg, prev) {
  if (!prev || prev.kind === 'system') return true;
  if (!!prev.out !== !!msg.out) return true;
  if ((prev.from || '') !== (msg.from || '')) return true;
  if ((prev.kind === 'bot') !== (msg.kind === 'bot')) return true;
  return msg.ts - prev.ts > GROUPING_MS;
}

/** Ticks das mensagens enviadas: relógio, ✓, ✓✓ cinza (entregue) ou azul (bot respondeu). */
export function tickHtml(m, size = '') {
  if (!m.out) return '';
  const cls = `tick ${size}`;
  switch (m.status) {
    case 'sending': return icon('clock', cls);
    case 'sent': return icon('check', cls);
    case 'answered': return `<span title="O bot respondeu">${icon('checks', cls + ' ok')}</span>`;
    case 'delivered': return `<span title="Entregue pelo servidor">${icon('checks', cls)}</span>`;
    case 'error': return icon('error', cls + ' err');
    default: return '';
  }
}

function botMessageHtml(m, chat, first, time) {
  const priv = chat.kind !== 'bot' ? `<span class="label-private">${icon('lock')} privada</span>` : '';
  const body = m.streaming && !m.text
    ? '<div class="thinking"><span class="dots"><i></i><i></i><i></i></span>consultando a LLM…</div>'
    : `<div class="md">${renderMarkdown(m.text)}${m.streaming ? '<span class="cursor"></span>' : ''}</div>`;
  const meta = m.meta || {};
  const info = m.streaming
    ? `<span class="info">${icon('bolt')} gerando…</span>`
    : `<span class="info" title="Modelo · tempo de resposta · turnos de histórico usados">${icon('chip')} ${escapeHtml(meta.model || '')}` +
      `${meta.elapsed_s != null ? ` · ${meta.elapsed_s}s` : ''}` +
      `${meta.history_turns != null ? ` · contexto ${meta.history_turns}/${meta.history_limit}` : ''}</span>`;
  return `<div class="msg in ${first ? 'first' : ''}" data-id="${escapeHtml(m.id)}">
    <div class="bubble bot">
      <div class="bot-head">${icon('robot', 'xs')}<span class="bot-name">${escapeHtml(m.from || 'bot')}</span>${priv}
        ${m.reqId ? `<span class="rid" title="Identificador da solicitação">${escapeHtml(m.reqId)}</span>` : ''}</div>
      ${body}
      <div class="meta">${info}<span>${time}</span></div>
    </div></div>`;
}

function botErrorHtml(m, first, time) {
  return `<div class="msg in ${first ? 'first' : ''}" data-id="${escapeHtml(m.id)}">
    <div class="bubble err">
      <div class="err-title">${icon('warning')} Falha na consulta${m.code ? ` (${escapeHtml(m.code)})` : ''}
        ${m.reqId ? `<span class="rid">${escapeHtml(m.reqId)}</span>` : ''}</div>
      <div class="text">${escapeHtml(m.text)}</div>
      ${m.question ? `<button class="retry" data-retry="${escapeHtml(m.id)}">${icon('refresh')} Tentar novamente</button>` : ''}
      <div class="meta"><span>${time}</span></div>
    </div></div>`;
}

function textMessageHtml(m, chat, first, time) {
  const showSender = chat.kind === 'group' && !m.out && first;
  const sender = showSender ? `<div class="sender" style="color:${hashColor(m.from)}">${escapeHtml(m.from)}</div>` : '';
  const priv = m.private
    ? `<div class="label-private">${icon('lock')} só o bot vê esta pergunta${m.reqId ? ` · ${escapeHtml(m.reqId)}` : ''}</div>` : '';
  const err = m.status === 'error' && m.error
    ? `<div class="msg-error">Não entregue: ${escapeHtml(m.error)}<span class="spacer"></span></div>` : '';
  return `<div class="msg ${m.out ? 'out' : 'in'} ${first ? 'first' : ''}" data-id="${escapeHtml(m.id)}">
    <div class="bubble">${sender}${priv}
      <div class="text">${formatWhats(m.text)}${err ? '' : '<span class="spacer"></span>'}</div>${err}
      <div class="meta"><span>${time}</span>${tickHtml(m)}</div>
    </div></div>`;
}

export function messageHtml(m, prev) {
  if (m.kind === 'system') return `<div class="pill ${m.variant || ''}" data-id="${escapeHtml(m.id)}">${m.html}</div>`;
  const chat = S.chats.get(m.chatId);
  const first = isFirst(m, prev);
  const time = fmtTime(m.ts);
  if (m.kind === 'bot') return botMessageHtml(m, chat, first, time);
  if (m.kind === 'bot-error') return botErrorHtml(m, first, time);
  return textMessageHtml(m, chat, first, time);
}
