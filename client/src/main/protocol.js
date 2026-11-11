'use strict';
/** Constantes do protocolo do SD Chat (ver docs/PROTOCOLO.md). */

const MAX_FRAME_BYTES = 64 * 1024;
const DELIMITER = 0x0a; // '\n'
const SERVER = 'server';

const FrameType = Object.freeze({
  HELLO: 'HELLO',
  WELCOME: 'WELCOME',
  PING: 'PING',
  BYE: 'BYE',
});

const Ports = Object.freeze({ TLS: 5443, PLAIN: 5000 });

module.exports = { MAX_FRAME_BYTES, DELIMITER, SERVER, FrameType, Ports };
