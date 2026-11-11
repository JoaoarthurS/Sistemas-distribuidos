/* Criação das conversas e dos avisos de segurança no topo de cada uma. */
import { GROUP_ID } from './constants.js';
import { icon } from './icons.js';
import { pushMessage, S, userOf } from './store.js';
import { chatIdFor, escapeHtml } from './utils.js';

function newChat(id, kind, name, lastTs) {
  return { id, kind, name, messages: [], unread: 0, lastTs, typing: new Map() };
}

export function ensureGroup() {
  if (!S.chats.has(GROUP_ID)) {
    const chat = newChat(GROUP_ID, 'group', 'Sala Geral', Date.now() + 2);
    S.chats.set(GROUP_ID, chat);
    addSecurityNotices(chat);
  }
  return S.chats.get(GROUP_ID);
}

export function ensureChat(name, role) {
  const id = chatIdFor(name);
  let chat = S.chats.get(id);
  if (!chat) {
    const kind = role === 'bot' ? 'bot' : 'dm';
    chat = newChat(id, kind, name, kind === 'bot' ? Date.now() + 1 : 0);
    S.chats.set(id, chat);
    addSecurityNotices(chat);
  }
  return chat;
}

const notice = (id, variant, html) => ({ id, kind: 'system', header: true, variant, html, ts: Date.now() });

function linkNotice(chat) {
  const tls = S.info && S.info.tls;
  if (S.secure && tls) {
    return notice('sec-' + chat.id, 'lock',
      `${icon('lock')}<span><b>Conexão protegida com ${escapeHtml(tls.protocol)}</b> (${escapeHtml(tls.cipher)}). ` +
      `O certificado do servidor foi validado pela CA <b>${escapeHtml(tls.ca)}</b>. As mensagens são cifradas ` +
      'entre você e o servidor, que as decifra para encaminhar.</span>');
  }
  return notice('sec-' + chat.id, 'lock warn',
    `${icon('unlock')}<span><b>Conexão sem criptografia.</b> Suas mensagens trafegam em texto puro ` +
    'até o servidor e podem ser lidas por quem capturar o tráfego (ex.: Wireshark).</span>');
}

function kindNotice(chat) {
  if (chat.kind === 'bot') {
    return notice('botinfo-' + chat.id, 'lock',
      `${icon('robot')}<span>As perguntas e respostas do assistente são <b>privadas</b>: o servidor entrega cada ` +
      'resposta apenas a você, vinculada pelo identificador da solicitação (<b>req_id</b>). ' +
      'Na Sala Geral, use <b>@bot pergunta</b>.</span>');
  }
  const u = chat.kind === 'dm' ? userOf(chat) : null;
  if (u && !u.secure) {
    return notice('peer-' + chat.id, 'lock warn',
      `${icon('unlock')}<span><b>${escapeHtml(u.name)}</b> está conectado(a) sem TLS: o trecho servidor → ${escapeHtml(u.name)} não é cifrado.</span>`);
  }
  return null;
}

function addSecurityNotices(chat) {
  for (const msg of [linkNotice(chat), kindNotice(chat)]) {
    if (msg) pushMessage(chat, msg, false);
  }
}
