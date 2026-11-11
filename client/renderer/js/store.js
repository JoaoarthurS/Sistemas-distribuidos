/* Estado da interface e operações que só mexem nele (sem DOM). */
import { DEFAULT_BOT, DEFAULT_MAX_TEXT, FRAME_LOG_MAX } from './constants.js';
import { key } from './utils.js';

export const S = {
  me: null,            // nome do usuário conectado
  opts: null,          // opções da última conexão bem-sucedida (para reconectar)
  info: null,          // dados do socket/TLS vindos do processo principal
  caPath: null,
  secure: false,
  connected: false,
  kicked: false,
  closeReason: '',
  maxText: DEFAULT_MAX_TEXT,
  users: new Map(),    // nome em minúsculas -> {name, role, secure, client, online}
  chats: new Map(),    // id -> conversa
  msgIndex: new Map(), // id da mensagem -> mensagem
  pending: new Map(),  // id do quadro MSG -> mensagem aguardando ACK
  requests: new Map(), // req_id -> {chatId, question, userMsgId}
  active: null,        // id da conversa aberta
  filter: 'all',
  frameLog: [],
  typingSent: { to: null, at: 0, timer: null },
  newBelow: 0,
};

// ------------------------------------------------------------------ usuários
export function upsertUser(u, online = true) {
  const k = key(u.name);
  const user = { ...(S.users.get(k) || {}), ...u, online };
  S.users.set(k, user);
  return user;
}

export function isBotName(name) {
  const u = S.users.get(key(name));
  return (u && u.role === 'bot') || key(name) === DEFAULT_BOT;
}

export const onlineHumans = () => [...S.users.values()].filter((u) => u.online && u.role === 'human');
export const hasBot = () => [...S.users.values()].some((u) => u.role === 'bot');

// ------------------------------------------------------------------ conversas
export const activeChat = () => S.chats.get(S.active);
export const userOf = (chat) => (chat && chat.kind !== 'group' ? S.users.get(key(chat.name)) : null);
export const lastRealMessage = (chat) => [...chat.messages].reverse().find((m) => m.kind !== 'system');
export const isBotStreaming = (chat) => chat.messages.some((m) => m.kind === 'bot' && m.streaming);

/** Adiciona uma mensagem à conversa (sem renderizar). */
export function pushMessage(chat, msg, countUnread = true) {
  msg.chatId = chat.id;
  chat.messages.push(msg);
  S.msgIndex.set(msg.id, msg);
  if (msg.kind !== 'system') chat.lastTs = Math.max(chat.lastTs, msg.ts || Date.now());
  if (countUnread && !msg.out && msg.kind !== 'system' && S.active !== chat.id) chat.unread += 1;
  return msg;
}

export function resetConversations() {
  S.chats.clear();
  S.msgIndex.clear();
  S.pending.clear();
  S.requests.clear();
  S.frameLog = [];
}

export function markAllOffline() {
  for (const u of S.users.values()) u.online = false;
}

// ------------------------------------------------------------------ registro de quadros
export function logFrame(dir, f) {
  S.frameLog.push({ dir, f, at: Date.now() });
  if (S.frameLog.length > FRAME_LOG_MAX) S.frameLog.shift();
}
