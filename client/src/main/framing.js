'use strict';
/**
 * Delimitação dos quadros (JSON + '\n'), sem dependência de sockets.
 *
 * O TCP entrega um fluxo de bytes: um evento 'data' pode conter meio quadro
 * ou vários. O decodificador acumula os bytes e cada '\n' fecha um quadro.
 */
const crypto = require('crypto');
const { DELIMITER, MAX_FRAME_BYTES } = require('./protocol');

class FrameTooLargeError extends Error {}

class FrameDecoder {
  constructor(maxBytes = MAX_FRAME_BYTES) {
    this.maxBytes = maxBytes;
    this.buffer = Buffer.alloc(0);
    this.invalid = 0; // quadros descartados por JSON inválido
  }

  /** Adiciona bytes recebidos e devolve os quadros completos já decodificados. */
  push(chunk) {
    this.buffer = this.buffer.length ? Buffer.concat([this.buffer, chunk]) : chunk;
    const frames = [];
    let idx;
    while ((idx = this.buffer.indexOf(DELIMITER)) !== -1) {
      const line = this.buffer.subarray(0, idx);
      this.buffer = this.buffer.subarray(idx + 1);
      if (line.length === 0) continue;
      try {
        frames.push(JSON.parse(line.toString('utf8')));
      } catch {
        this.invalid += 1; // quadro inválido é descartado
      }
    }
    return frames;
  }

  /** Verdadeiro se há mais bytes sem delimitador do que um quadro pode ter. */
  get overflowed() {
    return this.buffer.length > this.maxBytes;
  }

  reset() {
    this.buffer = Buffer.alloc(0);
    this.invalid = 0;
  }
}

function newId() {
  return crypto.randomBytes(6).toString('hex');
}

/** Completa id/ts e serializa um quadro com o delimitador. */
function encodeFrame(frame, maxBytes = MAX_FRAME_BYTES) {
  const full = { id: newId(), ts: Date.now(), ...frame };
  const data = Buffer.from(JSON.stringify(full) + '\n', 'utf8');
  if (data.length > maxBytes) throw new FrameTooLargeError('Mensagem grande demais.');
  return { frame: full, data };
}

module.exports = { FrameDecoder, FrameTooLargeError, encodeFrame, newId };
