/* Estado do painel (único lugar mutável). */

export const MAX_MESSAGES = 600;
export const MAX_EVENTS = 400;

export const state = { snap: null, messages: [], events: [], filter: 'all', search: '' };

export function resetFeed({ messages = [], events = [] }) {
  state.messages = messages;
  state.events = events;
}

function pushBounded(list, item, max) {
  list.push(item);
  if (list.length > max) list.shift();
}

export const addMessage = (m) => pushBounded(state.messages, m, MAX_MESSAGES);
export const addEvent = (e) => pushBounded(state.events, e, MAX_EVENTS);
