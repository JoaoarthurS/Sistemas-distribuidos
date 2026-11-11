'use strict';
/**
 * Conexão com o servidor do chat sobre um socket TCP (módulo `net`) ou TLS
 * (módulo `tls`) do Node.js.
 *
 * O Node é orientado a eventos: os dados chegam por callbacks ('data',
 * 'close', 'error'), então receber mensagens nunca bloqueia a digitação na
 * interface, que roda em outro processo (renderer) e conversa por IPC.
 */
const fs = require('fs');
const net = require('net');
const path = require('path');
const tls = require('tls');
const { EventEmitter } = require('events');
const { FrameDecoder, encodeFrame } = require('./framing');
const { describeError } = require('./errors');
const { FrameType, SERVER } = require('./protocol');

const PING_INTERVAL_MS = 25_000;
const CONNECT_TIMEOUT_MS = 8_000;

const emptyStats = () => ({ framesIn: 0, framesOut: 0, bytesIn: 0, bytesOut: 0 });

/** Cria o socket. O cliente confia SOMENTE na CA informada e valida o
 *  certificado do servidor (assinatura, validade e nome/IP no SAN). */
function openSocket({ host, port, secure, ca }) {
  if (!secure) return net.connect({ host, port });
  return tls.connect({
    host,
    port,
    ca,
    rejectUnauthorized: true,
    minVersion: 'TLSv1.2',
    servername: net.isIP(host) ? undefined : host,
  });
}

/** Dados exibidos no painel "Conexão e protocolo". */
function describeSocket(sock, { host, port, secure, caPath }) {
  const info = { host, port, secure, local: `${sock.localAddress}:${sock.localPort}` };
  if (!secure) return info;
  const cert = sock.getPeerCertificate();
  const cipher = sock.getCipher();
  info.tls = {
    protocol: sock.getProtocol(),
    cipher: cipher && (cipher.standardName || cipher.name),
    authorized: sock.authorized,
    subject: cert.subject && cert.subject.CN,
    issuer: cert.issuer && cert.issuer.CN,
    validTo: cert.valid_to,
    fingerprint: cert.fingerprint256,
    san: cert.subjectaltname,
    ca: path.basename(caPath),
  };
  return info;
}

/**
 * Eventos: 'frame' (quadro recebido) e 'closed' ({ reason }).
 */
class ChatConnection extends EventEmitter {
  constructor({ clientId, socketFactory = openSocket, pingIntervalMs = PING_INTERVAL_MS,
    connectTimeoutMs = CONNECT_TIMEOUT_MS } = {}) {
    super();
    this.clientId = clientId;
    this.socketFactory = socketFactory;
    this.pingIntervalMs = pingIntervalMs;
    this.connectTimeoutMs = connectTimeoutMs;
    this.socket = null;
    this.decoder = new FrameDecoder();
    this.pingTimer = null;
    this.info = null;
    this.stats = emptyStats();
    this.closeReason = null;
  }

  get connected() {
    return !!this.socket && !this.socket.destroyed;
  }

  /** Abre o socket, envia HELLO e resolve com o WELCOME (ou rejeita com o erro). */
  connect({ host, port, secure, caPath, name }) {
    this.close('nova conexão');
    this.decoder.reset();
    this.stats = emptyStats();
    this.closeReason = null;

    return new Promise((resolve, reject) => {
      let settled = false;
      const fail = (err) => {
        if (settled) return;
        settled = true;
        this.close('falha ao conectar');
        reject(err instanceof Error ? err : new Error(String(err)));
      };

      let ca;
      if (secure) {
        try {
          ca = fs.readFileSync(caPath);
        } catch {
          fail(new Error(`Não foi possível ler o certificado da CA (${caPath}).`));
          return;
        }
      }
      const sock = this.socketFactory({ host, port, secure, ca });
      this.socket = sock;
      sock.setNoDelay(true);
      sock.setTimeout(this.connectTimeoutMs, () => fail(new Error('Tempo esgotado ao conectar ao servidor.')));

      const onOpen = () => {
        sock.setTimeout(0);
        this.info = describeSocket(sock, { host, port, secure, caPath });
        const hello = this.send({
          type: FrameType.HELLO,
          from: name,
          to: SERVER,
          content: { role: 'human', client: this.clientId },
        });
        const onWelcome = (frame) => {
          if (frame.ref !== hello.id) return;
          this.off('frame', onWelcome);
          if (frame.type !== FrameType.WELCOME) {
            fail(new Error(frame.content || 'Servidor recusou a conexão.'));
            return;
          }
          settled = true;
          this._startHeartbeat();
          resolve({ welcome: frame, info: this.info });
        };
        this.on('frame', onWelcome);
      };

      sock.once(secure ? 'secureConnect' : 'connect', onOpen);
      sock.on('data', (chunk) => this._onData(chunk));
      sock.on('error', (err) => {
        if (!settled) return fail(new Error(describeError(err)));
        this.emit('closed', { reason: describeError(err) });
      });
      sock.on('close', () => {
        this._stopHeartbeat();
        if (!settled) return fail(new Error('A conexão foi encerrada pelo servidor.'));
        if (this.socket === sock) {
          this.socket = null;
          this.emit('closed', { reason: this.closeReason || 'Conexão com o servidor perdida.' });
        }
      });
    });
  }

  _onData(chunk) {
    this.stats.bytesIn += chunk.length;
    for (const frame of this.decoder.push(chunk)) {
      this.stats.framesIn += 1;
      this.emit('frame', frame);
    }
    if (this.decoder.overflowed) this.close('quadro acima do tamanho máximo');
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.pingTimer = setInterval(() => this.send({ type: FrameType.PING, to: SERVER }), this.pingIntervalMs);
  }

  _stopHeartbeat() {
    clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  /** Envia um quadro; devolve o quadro completo (com id/ts) ou null sem conexão. */
  send(frame) {
    if (!this.connected) return null;
    const { frame: full, data } = encodeFrame(frame);
    this.socket.write(data);
    this.stats.framesOut += 1;
    this.stats.bytesOut += data.length;
    return full;
  }

  /** Fecha a conexão; com reason 'logout' envia BYE antes (saída voluntária). */
  close(reason) {
    this._stopHeartbeat();
    const sock = this.socket;
    if (!sock) return;
    this.closeReason = reason;
    this.socket = null;
    try {
      if (!sock.destroyed && reason === 'logout') {
        sock.end(encodeFrame({ type: FrameType.BYE, to: SERVER }).data);
      } else {
        sock.destroy();
      }
    } catch {
      /* já fechado */
    }
  }

  snapshot() {
    return { ...this.info, stats: this.stats, connected: this.connected };
  }
}

module.exports = { ChatConnection, openSocket };
