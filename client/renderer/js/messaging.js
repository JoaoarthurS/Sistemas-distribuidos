/* Envio de quadros: mensagens (com status) e indicador "digitando…". */
import { bridge } from './bridge.js';
import { BROADCAST, FrameType, MENTION_RE, TYPING_IDLE_MS, TYPING_RESEND_MS } from './constants.js';
import { activeChat, isBotName, logFrame, S } from './store.js';
import { randomId } from './utils.js';
import { addMessage, updateMessage } from './views/conversation.js';
import { toast } from './views/feedback.js';

const destinationOf = (chat) => (chat.kind === 'group' ? BROADCAST : chat.name);

export async function sendFrame(frame) {
  const res = await bridge.send({ id: randomId(), from: S.me, ...frame });
  if (!res || res.error) return null;
  logFrame('out', res);
  return res;
}

/** Pergunta que o bot vai receber (sem a menção), ou null se não for para o bot. */
function botQuestion(chat, text) {
  const mention = MENTION_RE.exec(text);
  if (mention && isBotName(mention[1])) return mention[2];
  return chat.kind === 'bot' ? text : null;
}

export async function sendText(text, chatId = S.active) {
  const chat = S.chats.get(chatId);
  if (!chat || !S.connected) return;
  text = text.trim();
  if (!text) return;
  if (text.length > S.maxText) { toast(`A mensagem passa de ${S.maxText} caracteres.`, 'error'); return; }

  const question = botQuestion(chat, text);
  const id = randomId();
  const msg = {
    id, kind: 'text', from: S.me, text, ts: Date.now(), out: true, status: 'sending',
    private: question !== null && chat.kind !== 'bot',
    question,
  };
  S.pending.set(id, msg);
  addMessage(chat.id, msg);
  const sent = await sendFrame({ id, type: FrameType.MSG, to: destinationOf(chat), content: text });
  if (!sent) {
    msg.status = 'error';
    msg.error = 'sem conexão';
    S.pending.delete(id);
  } else if (msg.status === 'sending') {
    msg.status = 'sent'; // o ACK pode ter chegado antes da resposta do IPC
  }
  updateMessage(msg);
}

/** Avisa que o usuário está digitando (com limite de frequência). */
export function sendTyping() {
  const chat = activeChat();
  if (!chat || chat.kind === 'bot' || !S.connected) return;
  const to = destinationOf(chat);
  const t = S.typingSent;
  clearTimeout(t.timer);
  if (t.to !== to || Date.now() - t.at > TYPING_RESEND_MS) {
    sendFrame({ type: FrameType.TYPING, to, content: true });
    t.to = to;
    t.at = Date.now();
  }
  t.timer = setTimeout(stopTyping, TYPING_IDLE_MS);
}

export function stopTyping() {
  const t = S.typingSent;
  clearTimeout(t.timer);
  if (t.to && S.connected) sendFrame({ type: FrameType.TYPING, to: t.to, content: false });
  t.to = null;
  t.at = 0;
}
