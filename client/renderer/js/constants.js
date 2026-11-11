/* Constantes da interface. */

export const GROUP_ID = 'all';
export const BROADCAST = '*';
export const DEFAULT_BOT = 'bot';
export const NAME_RE = /^[A-Za-z0-9À-ÖØ-öø-ÿ_.\-]{2,20}$/;
export const MENTION_RE = /^\s*@([^\s,:]+)[\s,:]*([\s\S]*)$/;
export const DEFAULT_MAX_TEXT = 4000;

export const FRAME_LOG_MAX = 60;          // quadros guardados para o painel "Conexão e protocolo"
export const TYPING_RESEND_MS = 2500;     // reenvia TYPING=true no máximo a cada 2,5 s
export const TYPING_IDLE_MS = 4000;       // sem digitar por 4 s => TYPING=false
export const TYPING_EXPIRE_MS = 6000;     // indicador remoto some se não vier TYPING=false
export const TOAST_MS = 4200;

export const EMOJIS = ['😀', '😂', '😅', '😍', '🤔', '😎', '😢', '😡', '👍', '👏', '🙏', '🙌', '🔥', '🎉', '❤️', '✅',
  '❌', '🚀', '💡', '📌', '🔒', '🤖', '💻', '📡', '🧵', '⏱️', '👀', '🤝', '⭐', '☕', '📚', '✍️'];

export const BOT_SUGGESTIONS = [
  'Explique a diferença entre TCP e UDP',
  'O que é um socket?',
  'Como o TLS protege as mensagens?',
  'Para que servem threads em um servidor?',
  '/ajuda',
];

/** Tipos de quadro do protocolo usados pela interface. */
export const FrameType = Object.freeze({
  MSG: 'MSG', TYPING: 'TYPING', ACK: 'ACK', ERROR: 'ERROR', SYSTEM: 'SYSTEM',
  USER_JOINED: 'USER_JOINED', USER_LEFT: 'USER_LEFT', USER_LIST: 'USER_LIST',
  BOT_TYPING: 'BOT_TYPING', BOT_CHUNK: 'BOT_CHUNK', BOT_RESPONSE: 'BOT_RESPONSE', BOT_ERROR: 'BOT_ERROR',
});
