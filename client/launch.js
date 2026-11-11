'use strict';
// Inicia o Electron garantindo um ambiente limpo. Terminais abertos a partir
// de algumas ferramentas (ex.: extensões do VS Code) herdam
// ELECTRON_RUN_AS_NODE=1, o que faria o Electron rodar como Node puro.
//   uso: npm start -- --name=Ana [--plain] [--port=5443] [--host=127.0.0.1] [--autoconnect]
const { spawn } = require('child_process');
const electron = require('electron'); // fora do Electron, retorna o caminho do executável

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electron, ['.', ...process.argv.slice(2)], { cwd: __dirname, env, stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 0));
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig));
