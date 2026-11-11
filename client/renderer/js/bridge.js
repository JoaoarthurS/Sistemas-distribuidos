/*
 * Ponte com o processo principal (exposta pelo preload.js via contextBridge).
 * A interface não tem acesso à rede: tudo passa por estas funções, e só este
 * módulo conhece window.chat.
 */
export const bridge = window.chat;
