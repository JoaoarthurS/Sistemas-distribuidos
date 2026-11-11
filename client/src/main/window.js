'use strict';
/** Janela principal do cliente. */
const fs = require('fs');
const path = require('path');
const { BrowserWindow, nativeTheme } = require('electron');

const CLIENT_DIR = path.join(__dirname, '..', '..');

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 760,
    minHeight: 520,
    title: 'SD Chat',
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#0b141a' : '#eae6df',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(CLIENT_DIR, 'preload.js'),
      contextIsolation: true,   // a interface não acessa o Node: só a ponte do preload
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.loadFile(path.join(CLIENT_DIR, 'renderer', 'index.html'));
  win.once('ready-to-show', () => win.show());
  return win;
}

/**
 * Captura de tela opcional (gera imagens para o relatório):
 *   SDCHAT_SCREENSHOT=arquivo.png SDCHAT_SCREENSHOT_DELAY=8000 npm start
 */
function scheduleScreenshot(win, env, onDone) {
  if (!env.SDCHAT_SCREENSHOT) return;
  const delay = Number(env.SDCHAT_SCREENSHOT_DELAY || 6000);
  setTimeout(async () => {
    const img = await win.webContents.capturePage();
    fs.writeFileSync(env.SDCHAT_SCREENSHOT, img.toPNG());
    if (env.SDCHAT_SCREENSHOT_QUIT) onDone();
  }, delay);
}

module.exports = { createMainWindow, scheduleScreenshot };
