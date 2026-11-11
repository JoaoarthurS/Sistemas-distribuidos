/*
 * Tratamento dos quadros recebidos do servidor.
 *
 * Cada tipo tem um tratador na tabela HANDLERS: suportar um tipo novo é
 * acrescentar uma entrada, sem mexer em handleFrame (aberto/fechado).
 */
import { ensureChat, ensureGroup } from './chats.js';
import { BROADCAST, FrameType, GROUP_ID, TYPING_EXPIRE_MS } from './constants.js';
import { logFrame, S, upsertUser } from './store.js';
import { chatIdFor, escapeHtml, key, randomId } from './utils.js';
import { renderChatList } from './views/chat-list.js';
import { addMessage, refreshPresence, renderHeader, systemNote, updateMessage } from './views/conversation.js';
import { toast } from './views/feedback.js';

// ------------------------------------------------------------------ apoio ao bot
/** Mensagem do bot ligada ao req_id (criada no primeiro quadro recebido). */
function botMessageFor(f) {
  const id = 'bot-' + f.req_id;
  const existing = S.msgIndex.get(id);
  if (existing) return existing;
  const req = S.requests.get(f.req_id);
  const chatId = req ? req.chatId : ensureChat(f.from, 'bot').id;
  const m = { id, kind: 'bot', from: f.from, text: '', ts: f.ts || Date.now(), out: false, reqId: f.req_id, streaming: true };
  addMessage(chatId, m);
  return m;
}

/** ✓✓ azul na pergunta respondida. */
function markAnswered(reqId) {
  const req = S.requests.get(reqId);
  const userMsg = req && S.msgIndex.get(req.userMsgId);
  if (userMsg) { userMsg.status = 'answered'; updateMessage(userMsg); }
}

/** Conversa e pergunta original de um BOT_ERROR (para o botão "Tentar novamente"). */
function botErrorOrigin(f) {
  if (f.req_id && S.requests.has(f.req_id)) {
    const req = S.requests.get(f.req_id);
    return { chatId: req.chatId, question: req.question };
  }
  if (f.ref && S.pending.has(f.ref)) { // falhou antes de virar solicitação (ex.: BOT_OFFLINE)
    const um = S.pending.get(f.ref);
    S.pending.delete(f.ref);
    um.status = 'delivered';
    updateMessage(um);
    return { chatId: um.chatId, question: um.question };
  }
  return { chatId: ensureChat(f.from || 'bot', 'bot').id, question: null };
}

// ------------------------------------------------------------------ tratadores
const HANDLERS = {
  [FrameType.MSG](f) {
    const chat = f.to === BROADCAST ? ensureGroup() : ensureChat(f.from, 'human');
    chat.typing.delete(f.from);
    addMessage(chat.id, { id: f.id || randomId(), kind: 'text', from: f.from, text: String(f.content), ts: f.ts || Date.now(), out: false });
    if (S.active === chat.id) renderHeader();
  },

  [FrameType.ACK](f) {
    const m = S.pending.get(f.ref);
    if (!m) return;
    S.pending.delete(f.ref);
    m.status = 'delivered';
    if (f.req_id) {
      m.reqId = f.req_id;
      S.requests.set(f.req_id, { chatId: m.chatId, question: m.question, userMsgId: m.id });
    }
    updateMessage(m);
  },

  [FrameType.ERROR](f) {
    const m = f.ref && S.pending.get(f.ref);
    if (m) {
      S.pending.delete(f.ref);
      m.status = 'error';
      m.error = f.content;
      updateMessage(m);
    }
    toast(f.content || 'Erro do servidor', 'error');
  },

  [FrameType.BOT_TYPING](f) {
    botMessageFor(f);
    refreshPresence();
  },

  [FrameType.BOT_CHUNK](f) {
    const m = botMessageFor(f);
    m.text += f.content || '';
    updateMessage(m);
  },

  [FrameType.BOT_RESPONSE](f) {
    const m = botMessageFor(f);
    Object.assign(m, { text: String(f.content || ''), streaming: false, meta: f.meta || null, ts: f.ts || m.ts });
    updateMessage(m);
    markAnswered(f.req_id);
    refreshPresence();
  },

  [FrameType.BOT_ERROR](f) {
    const { chatId, question } = botErrorOrigin(f);
    const errMsg = {
      id: 'err-' + (f.req_id || randomId()), kind: 'bot-error', from: f.from, text: String(f.content || 'Falha'),
      code: f.code, reqId: f.req_id, ts: f.ts || Date.now(), out: false, question, retryChat: chatId,
    };
    const streaming = f.req_id && S.msgIndex.get('bot-' + f.req_id);
    if (streaming) {
      Object.assign(streaming, errMsg, { id: streaming.id, streaming: false });
      updateMessage(streaming);
    } else {
      addMessage(chatId, errMsg);
    }
    refreshPresence();
  },

  [FrameType.USER_JOINED](f) {
    const u = upsertUser(f.content, true);
    if (u.name !== S.me) {
      ensureChat(u.name, u.role);
      systemNote(GROUP_ID, u.role === 'bot' ? `🤖 ${u.name} (assistente) entrou` : `${u.name} entrou${u.secure ? ' 🔒' : ' (sem criptografia)'}`);
    }
    refreshPresence();
  },

  [FrameType.USER_LEFT](f) {
    const c = f.content || {};
    const u = S.users.get(key(c.name));
    if (u) u.online = false;
    const chat = S.chats.get(chatIdFor(c.name));
    if (chat) chat.typing.clear();
    systemNote(GROUP_ID, `${c.name} saiu${c.reason ? ` (${c.reason})` : ''}`);
    if (chat && chat.kind === 'dm') systemNote(chat.id, `${c.name} desconectou`);
    refreshPresence();
  },

  [FrameType.USER_LIST](f) {
    for (const u of f.content || []) if (u.name !== S.me) upsertUser(u, true);
    refreshPresence();
  },

  [FrameType.TYPING](f) {
    const chat = f.to === BROADCAST ? S.chats.get(GROUP_ID) : S.chats.get(chatIdFor(f.from));
    if (!chat) return;
    if (f.content) chat.typing.set(f.from, Date.now() + TYPING_EXPIRE_MS);
    else chat.typing.delete(f.from);
    renderChatList();
    if (S.active === chat.id) renderHeader();
  },

  [FrameType.SYSTEM](f) {
    if (f.code === 'KICKED') S.kicked = true;
    addMessage(GROUP_ID, { id: 'sys-' + (f.id || randomId()), kind: 'system', variant: 'server', html: `📢 <b>Servidor:</b> ${escapeHtml(f.content)}`, ts: Date.now() }, false);
    toast(`Servidor: ${f.content}`, 'info');
  },
};

export function handleFrame(f) {
  logFrame('in', f);
  if (!S.me) return; // ainda no login: o erro do HELLO já aparece no formulário
  const handler = HANDLERS[f.type];
  if (handler) handler(f); // PONG e outros tipos não exigem ação
}

/** Remove indicadores de "digitando…" que não receberam TYPING=false. */
export function expireTyping() {
  let changed = false;
  for (const c of S.chats.values()) {
    for (const [name, exp] of c.typing) if (exp < Date.now()) { c.typing.delete(name); changed = true; }
  }
  if (changed) { renderChatList(); if (S.active) renderHeader(); }
}
