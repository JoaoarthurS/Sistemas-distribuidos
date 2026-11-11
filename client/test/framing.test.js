'use strict';
/* Testes da delimitação de quadros do cliente (node --test). */
const test = require('node:test');
const assert = require('node:assert/strict');
const { FrameDecoder, FrameTooLargeError, encodeFrame } = require('../src/main/framing');
const { loginDefaults, parseArgs } = require('../src/main/config');
const { describeError } = require('../src/main/errors');

test('quadros partidos e agrupados são separados pelo \\n', () => {
  const a = encodeFrame({ type: 'MSG', content: 'olá 🚀\nsegunda linha' }).data;
  const b = encodeFrame({ type: 'PING' }).data;
  const stream = Buffer.concat([a, b]);
  const dec = new FrameDecoder();
  assert.deepEqual(dec.push(stream.subarray(0, 5)), []);
  const frames = dec.push(stream.subarray(5));
  assert.deepEqual(frames.map((f) => f.type), ['MSG', 'PING']);
  assert.equal(frames[0].content, 'olá 🚀\nsegunda linha');
});

test('JSON inválido é descartado sem afetar os próximos quadros', () => {
  const dec = new FrameDecoder();
  const frames = dec.push(Buffer.from('{quebrado}\n{"type":"PONG"}\n'));
  assert.deepEqual(frames, [{ type: 'PONG' }]);
  assert.equal(dec.invalid, 1);
});

test('buffer sem delimitador acima do limite é sinalizado', () => {
  const dec = new FrameDecoder(10);
  dec.push(Buffer.from('x'.repeat(11)));
  assert.equal(dec.overflowed, true);
});

test('encodeFrame completa id/ts e recusa quadros grandes demais', () => {
  const { frame, data } = encodeFrame({ type: 'MSG', content: 'oi' });
  assert.match(frame.id, /^[0-9a-f]{12}$/);
  assert.equal(data.at(-1), 0x0a);
  assert.throws(() => encodeFrame({ type: 'MSG', content: 'x'.repeat(100) }, 50), FrameTooLargeError);
});

test('argumentos de linha de comando viram os valores do login', () => {
  const d = loginDefaults(parseArgs(['--name=Carla', '--plain', '--autoconnect']), '/ca.crt');
  assert.deepEqual(d, { name: 'Carla', host: '127.0.0.1', secure: false, port: 5000, caPath: '/ca.crt', autoconnect: true, theme: null });
  assert.equal(loginDefaults(parseArgs([]), '/ca.crt').port, 5443);
});

test('erros conhecidos de rede/TLS têm mensagem amigável', () => {
  assert.match(describeError({ code: 'ECONNREFUSED' }), /recusou/);
  assert.equal(describeError(new Error('outro')), 'outro');
});
