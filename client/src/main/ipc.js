'use strict';
/**
 * Canais IPC entre a interface (renderer) e o processo principal.
 * Cada canal tem um único tratador; o renderer nunca acessa o socket.
 */
const path = require('path');

const Channels = Object.freeze({
  DEFAULTS: 'app:defaults',
  PICK_CA: 'app:pick-ca',
  CONNECT: 'chat:connect',
  SEND: 'chat:send',
  DISCONNECT: 'chat:disconnect',
  INFO: 'chat:info',
  FRAME: 'chat:frame',
  CLOSED: 'chat:closed',
});

function registerIpcHandlers({ ipcMain, dialog, connection, getWindow, defaults }) {
  ipcMain.handle(Channels.DEFAULTS, () => defaults);

  ipcMain.handle(Channels.PICK_CA, async () => {
    const res = await dialog.showOpenDialog(getWindow(), {
      title: 'Certificado da autoridade certificadora (CA)',
      defaultPath: path.dirname(defaults.caPath),
      filters: [{ name: 'Certificados', extensions: ['crt', 'pem', 'cer'] }],
      properties: ['openFile'],
    });
    return res.canceled ? null : res.filePaths[0];
  });

  ipcMain.handle(Channels.CONNECT, async (_e, opts) => {
    try {
      const { welcome, info } = await connection.connect(opts);
      return { ok: true, welcome, info };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  });

  ipcMain.handle(Channels.SEND, (_e, frame) => {
    try {
      return connection.send(frame);
    } catch (err) {
      return { error: err.message };
    }
  });

  ipcMain.handle(Channels.DISCONNECT, () => {
    connection.close('logout');
    return true;
  });

  ipcMain.handle(Channels.INFO, () => connection.snapshot());
}

/** Repassa os eventos da conexão para a janela aberta. */
function forwardConnectionEvents(connection, getWindow) {
  const toWindow = (channel) => (payload) => {
    const win = getWindow();
    if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
  };
  connection.on('frame', toWindow(Channels.FRAME));
  connection.on('closed', toWindow(Channels.CLOSED));
}

module.exports = { Channels, registerIpcHandlers, forwardConnectionEvents };
