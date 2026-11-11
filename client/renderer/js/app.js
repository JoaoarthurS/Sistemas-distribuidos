/* ==========================================================================
   SD Chat — interface do cliente humano (renderer do Electron).

   Não tem acesso à rede: envia e recebe quadros do protocolo pela ponte
   `window.chat` (preload.js → bridge.js), que conversa com o processo
   principal, dono do socket TCP/TLS.

   Módulos:
     store.js           estado da interface
     chats.js           criação de conversas e avisos de segurança
     frame-handlers.js  tratamento de cada tipo de quadro recebido
     messaging.js       envio de mensagens e "digitando…"
     session.js         login, reconexão, queda e saída
     navigation.js      troca de conversa
     events.js          ligação dos eventos do DOM
     views/             renderização (lista, conversa, login, painel...)
     format.js          formatação estilo WhatsApp e Markdown do bot
   ========================================================================== */
import { bridge } from './bridge.js';
import { bindEvents } from './events.js';
import { icon } from './icons.js';
import { doLogin } from './session.js';
import { S } from './store.js';
import { applyTheme, initialTheme } from './views/feedback.js';
import { fillLoginForm } from './views/login.js';

async function init() {
  document.querySelectorAll('[data-icon]').forEach((el) => { el.outerHTML = icon(el.dataset.icon); });
  const defaults = await bridge.defaults();
  applyTheme(initialTheme(defaults.theme));
  S.caPath = defaults.caPath;
  fillLoginForm(defaults);
  bindEvents();
  if (defaults.autoconnect && defaults.name) doLogin();
  else document.getElementById('f-name').focus();
}

init();
