'use strict';
// Ponte segura entre a interface (renderer, sem acesso ao Node) e o processo
// principal, que é quem controla o socket.
// Os nomes dos canais espelham src/main/ipc.js (Channels): um preload com
// sandbox só pode importar o módulo 'electron', não arquivos do projeto.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('chat', {
  defaults: () => ipcRenderer.invoke('app:defaults'),
  pickCA: () => ipcRenderer.invoke('app:pick-ca'),
  connect: (opts) => ipcRenderer.invoke('chat:connect', opts),
  send: (frame) => ipcRenderer.invoke('chat:send', frame),
  disconnect: () => ipcRenderer.invoke('chat:disconnect'),
  info: () => ipcRenderer.invoke('chat:info'),
  onFrame: (cb) => ipcRenderer.on('chat:frame', (_e, frame) => cb(frame)),
  onClosed: (cb) => ipcRenderer.on('chat:closed', (_e, info) => cb(info)),
});
