/* Sessão: login, início da sessão, reconexão, queda da conexão e saída. */
import { bridge } from './bridge.js';
import { ensureChat, ensureGroup } from './chats.js';
import { DEFAULT_BOT, DEFAULT_MAX_TEXT, GROUP_ID } from './constants.js';
import { stopTyping } from './messaging.js';
import { openChat } from './navigation.js';
import { hasBot, markAllOffline, resetConversations, S, upsertUser } from './store.js';
import { renderChatList, updateTitle } from './views/chat-list.js';
import { refreshPresence, renderBanner, renderComposer, renderHeader, systemNote, updateMessage } from './views/conversation.js';
import { closeDrawer } from './views/drawer.js';
import { toast } from './views/feedback.js';
import { readLoginForm, setLoginBusy, showLogin, showLoginError } from './views/login.js';
import { renderMe } from './views/profile.js';

async function connectWith(opts) {
  const res = await bridge.connect(opts);
  if (res.ok) S.opts = opts;
  return res;
}

function startSession(welcome, info, reconnecting = false) {
  const c = welcome.content;
  Object.assign(S, { me: c.name, secure: !!c.secure, info, connected: true, kicked: false, maxText: c.max_text || DEFAULT_MAX_TEXT });
  markAllOffline();
  for (const u of c.users) if (u.name !== S.me) upsertUser(u, true);
  if (!reconnecting) resetConversations();
  ensureGroup();
  for (const u of S.users.values()) ensureChat(u.name, u.role);
  if (!hasBot()) {
    // a conversa com o bot existe mesmo com ele offline (mostra BOT_OFFLINE)
    upsertUser({ name: DEFAULT_BOT, role: 'bot', secure: true, client: '' }, false);
    ensureChat(DEFAULT_BOT, 'bot');
  }
  if (reconnecting) systemNote(GROUP_ID, 'Reconectado ao servidor');

  showLogin(false);
  renderMe();
  renderChatList();
  updateTitle();
  if (!S.active || !S.chats.has(S.active)) openChat(GROUP_ID);
  else { renderHeader(); renderComposer(); renderBanner(); }
}

export async function doLogin(ev) {
  if (ev) ev.preventDefault();
  const { opts, error } = readLoginForm(S.caPath);
  if (error) return showLoginError(error);
  showLoginError('');
  setLoginBusy(true);
  const res = await connectWith(opts);
  setLoginBusy(false);
  if (!res.ok) return showLoginError(res.error);
  startSession(res.welcome, res.info);
}

export async function reconnect() {
  if (!S.opts) return;
  const btn = document.getElementById('btn-reconnect');
  if (btn) { btn.disabled = true; btn.textContent = 'Reconectando…'; }
  const res = await connectWith(S.opts);
  if (res.ok) {
    startSession(res.welcome, res.info, true);
    toast('Reconectado!', 'ok');
  } else {
    S.closeReason = res.error;
    renderBanner();
    toast(res.error, 'error');
  }
}

export async function logout() {
  stopTyping();
  await bridge.disconnect();
  Object.assign(S, { me: null, connected: false, active: null });
  resetConversations();
  S.users.clear();
  closeDrawer();
  showLogin(true);
  document.title = 'SD Chat';
}

/** O processo principal avisou que o socket fechou. */
export function handleClosed(info) {
  if (!S.me) return;
  S.connected = false;
  S.closeReason = S.kicked ? 'Você foi desconectado pelo administrador.' : (info && info.reason) || '';
  markAllOffline();
  for (const m of S.pending.values()) { m.status = 'error'; m.error = 'conexão perdida'; updateMessage(m); }
  S.pending.clear();
  for (const m of S.msgIndex.values()) {
    if (m.kind === 'bot' && m.streaming) {
      m.streaming = false;
      m.text = m.text || '(resposta interrompida: conexão perdida)';
      updateMessage(m);
    }
  }
  for (const c of S.chats.values()) c.typing.clear();
  renderMe();
  refreshPresence();
  renderBanner();
  toast('Conexão com o servidor perdida.', 'error');
}
