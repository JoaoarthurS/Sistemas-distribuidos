/* Painel lateral "Conexão e protocolo": TLS, certificado, tráfego e quadros ao vivo. */
import { bridge } from '../bridge.js';
import { $ } from '../dom.js';
import { icon } from '../icons.js';
import { S } from '../store.js';
import { escapeHtml, fmtBytes } from '../utils.js';

const REFRESH_MS = 1000;
const FRAMES_SHOWN = 25;
let timer = null;

export const isDrawerOpen = () => $('#drawer').classList.contains('open');

export function openDrawer() {
  $('#drawer').classList.add('open');
  $('#drawer').setAttribute('aria-hidden', 'false');
  renderDrawer();
  clearInterval(timer);
  timer = setInterval(renderDrawer, REFRESH_MS);
}

export function closeDrawer() {
  $('#drawer').classList.remove('open');
  $('#drawer').setAttribute('aria-hidden', 'true');
  clearInterval(timer);
}

export function toggleDrawer() {
  if (isDrawerOpen()) closeDrawer();
  else openDrawer();
}

function heroHtml(info) {
  const tls = info.tls;
  if (info.secure && tls) {
    return `<div class="d-hero"><div class="big on">${icon('lock')}</div><div><b>Conexão protegida (TLS)</b>
      <span>${escapeHtml(tls.protocol)} · ${escapeHtml(tls.cipher)}<br>Cifrado entre este cliente e o servidor; o servidor decifra para rotear.</span></div></div>`;
  }
  return `<div class="d-hero"><div class="big off">${icon('unlock')}</div><div><b>Sem criptografia (TCP puro)</b>
    <span>O conteúdo JSON aparece legível em uma captura do Wireshark. Use apenas como referência.</span></div></div>`;
}

function detailsHtml(info) {
  const tls = info.tls;
  const rows = [
    ['Estado', info.connected ? 'conectado' : 'desconectado'],
    ['Servidor', `${info.host}:${info.port}`],
    ['Endereço local', info.local],
    ['Transporte', `TCP · socket do Node.js (módulo ${info.secure ? 'tls' : 'net'})`],
  ];
  if (tls) {
    rows.push(['Protocolo', tls.protocol], ['Cifra', tls.cipher],
      ['Certificado', `CN=${tls.subject}`], ['Emitido por', `CN=${tls.issuer}`],
      ['Válido até', tls.validTo], ['SAN', tls.san], ['CA confiável', tls.ca],
      ['Validação', tls.authorized ? '✔ cadeia e nome verificados' : '✖ não validado']);
  }
  let html = rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v ?? '—')}</dd>`).join('');
  if (tls) html += `<dt>SHA-256</dt><dd><span class="mono">${escapeHtml(tls.fingerprint)}</span></dd>`;
  return html;
}

function frameLogHtml() {
  return S.frameLog.slice(-FRAMES_SHOWN).reverse().map(({ dir, f }) => {
    const dim = f.type === 'PING' || f.type === 'PONG' ? 'dim' : '';
    const route = `${f.from || S.me || ''} → ${f.to ?? ''}`;
    const extra = f.req_id ? ` · ${f.req_id}` : '';
    const content = typeof f.content === 'string' ? ` · "${f.content.slice(0, 50)}"` : '';
    return `<div class="fl ${dim}" title="${escapeHtml(JSON.stringify(f))}"><span class="dir ${dir}">${dir === 'in' ? '⬇' : '⬆'}</span>
      <span class="t">${escapeHtml(f.type)}</span><span class="d">${escapeHtml(route + extra + content)}</span></div>`;
  }).join('');
}

async function renderDrawer() {
  const info = await bridge.info();
  const st = info.stats || { framesIn: 0, framesOut: 0, bytesIn: 0, bytesOut: 0 };
  const frames = frameLogHtml();
  $('#drawer-body').innerHTML = `
    <div class="d-section">${heroHtml(info)}</div>
    <div class="d-section"><h4>Detalhes</h4><dl class="kv">${detailsHtml(info)}</dl></div>
    <div class="d-section"><h4>Tráfego nesta sessão</h4><div class="stats4">
      <div class="stat"><b>${st.framesOut}</b><span>quadros enviados</span></div>
      <div class="stat"><b>${st.framesIn}</b><span>quadros recebidos</span></div>
      <div class="stat"><b>${fmtBytes(st.bytesOut)}</b><span>bytes enviados</span></div>
      <div class="stat"><b>${fmtBytes(st.bytesIn)}</b><span>bytes recebidos</span></div></div></div>
    <div class="d-section"><h4>Protocolo ao vivo (últimos quadros)</h4>
      <p class="note" style="margin-bottom:10px">Cada quadro é um objeto JSON terminado por <b>\\n</b>, com
      <b>type</b>, <b>from</b>, <b>to</b>, <b>content</b>, <b>id</b> e <b>req_id</b> (solicitações ao bot).
      Passe o mouse sobre um quadro para ver o JSON completo.</p>
      <div class="frame-log">${frames || '<p class="note">Nenhum quadro ainda.</p>'}</div></div>`;
}
