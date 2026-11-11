'use strict';
/**
 * Processo principal do cliente humano (Electron) — raiz de composição.
 *
 * Toda a comunicação de rede fica aqui (src/main/connection.js): socket TCP
 * ou TLS do Node.js, delimitação dos quadros e heartbeat. A interface
 * (renderer/) roda em outro processo e conversa com este por IPC.
 */
const path = require('path');
const fs = require('fs');
const { app, ipcMain, dialog } = require('electron');
const { ChatConnection } = require('./src/main/connection');
const { parseArgs, loginDefaults } = require('./src/main/config');
const { registerIpcHandlers, forwardConnectionEvents } = require('./src/main/ipc');
const { createMainWindow, scheduleScreenshot } = require('./src/main/window');

// Cada instância usa um perfil próprio: várias janelas (Ana, Bruno, Carla)
// podem rodar ao mesmo tempo na mesma máquina.
const profileDir = path.join(app.getPath('temp'), `sd-chat-${process.pid}`);
app.setPath('userData', profileDir);

const defaults = loginDefaults(parseArgs(process.argv.slice(1)));
const connection = new ChatConnection({ clientId: `electron/${process.versions.electron}` });
let win = null;
const getWindow = () => win;

forwardConnectionEvents(connection, getWindow);
registerIpcHandlers({ ipcMain, dialog, connection, getWindow, defaults });

app.whenReady().then(() => {
  win = createMainWindow();
  scheduleScreenshot(win, process.env, () => app.quit());
});

app.on('window-all-closed', () => {
  connection.close('logout');
  app.quit();
});

app.on('quit', () => {
  try {
    fs.rmSync(profileDir, { recursive: true, force: true });
  } catch {
    /* o Chromium pode manter arquivos abertos; é só uma pasta temporária */
  }
});
