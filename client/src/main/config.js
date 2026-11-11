'use strict';
/** Argumentos de linha de comando do cliente e valores iniciais do login. */
const path = require('path');
const { Ports } = require('./protocol');

const DEFAULT_CA = path.join(__dirname, '..', '..', '..', 'certs', 'ca.crt');

/** --chave=valor vira { chave: 'valor' }; --flag vira { flag: true }. */
function parseArgs(argv) {
  const out = {};
  for (const arg of argv) {
    const m = /^--([\w-]+)(?:=(.*))?$/.exec(arg);
    if (m) out[m[1]] = m[2] === undefined ? true : m[2];
  }
  return out;
}

const str = (v, fallback) => (typeof v === 'string' ? v : fallback);

/** Valores que preenchem a tela de login (e o --autoconnect). */
function loginDefaults(args, defaultCa = DEFAULT_CA) {
  const plain = !!args.plain;
  return {
    name: str(args.name, ''),
    host: str(args.host, '127.0.0.1'),
    secure: !plain,
    port: args.port ? Number(args.port) : plain ? Ports.PLAIN : Ports.TLS,
    caPath: typeof args.ca === 'string' ? path.resolve(args.ca) : defaultCa,
    autoconnect: !!args.autoconnect,
    theme: str(args.theme, null),
  };
}

module.exports = { DEFAULT_CA, parseArgs, loginDefaults };
