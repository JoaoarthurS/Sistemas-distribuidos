/* Troca da conversa aberta. */
import { $ } from './dom.js';
import { stopTyping } from './messaging.js';
import { S } from './store.js';
import { renderChatList, updateTitle } from './views/chat-list.js';
import { closePopups } from './views/composer.js';
import { renderBanner, renderComposer, renderHeader, renderMessages } from './views/conversation.js';

export function openChat(id) {
  const chat = S.chats.get(id);
  if (!chat) return;
  stopTyping();
  S.active = id;
  chat.unread = 0;
  $('#empty').hidden = true;
  $('#chat').hidden = false;
  closePopups();
  renderHeader();
  renderMessages();
  renderComposer();
  renderBanner();
  renderChatList();
  updateTitle();
  $('#input').focus();
}
