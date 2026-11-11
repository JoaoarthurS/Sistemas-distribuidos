'use strict';
/** Tradução dos erros de rede/TLS do Node.js para mensagens ao usuário. */

const MESSAGES = Object.freeze({
  ECONNREFUSED: 'Servidor recusou a conexão — ele está rodando nesta porta?',
  ECONNRESET: 'A conexão foi reiniciada pelo servidor.',
  ETIMEDOUT: 'Tempo esgotado ao contatar o servidor.',
  ENOTFOUND: 'Endereço do servidor não encontrado.',
  EHOSTUNREACH: 'Servidor inalcançável.',
  UNABLE_TO_VERIFY_LEAF_SIGNATURE: 'Certificado do servidor não foi emitido pela CA configurada.',
  SELF_SIGNED_CERT_IN_CHAIN: 'Certificado do servidor não confiável (CA diferente).',
  DEPTH_ZERO_SELF_SIGNED_CERT: 'Certificado do servidor é autoassinado e não confiável.',
  CERT_HAS_EXPIRED: 'O certificado do servidor expirou.',
  ERR_TLS_CERT_ALTNAME_INVALID: 'O certificado não é válido para este endereço (SAN).',
});

function describeError(err) {
  return MESSAGES[err && err.code] || (err && err.message) || String(err);
}

module.exports = { describeError };
