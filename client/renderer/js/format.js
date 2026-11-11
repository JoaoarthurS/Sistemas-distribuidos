/* Formatação de texto das mensagens — sempre escapando o HTML antes. */
import { escapeHtml } from './utils.js';

/** Formatação estilo WhatsApp: *negrito*, _itálico_, ~riscado~, `código`. */
export function formatWhats(text) {
  const codes = [];
  const stash = (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; };
  let s = escapeHtml(text);
  s = s.replace(/```([\s\S]+?)```/g, stash);
  s = s.replace(/`([^`\n]+)`/g, stash);
  s = s.replace(/(^|[\s(])\*(?!\s)([^*\n]+?)\*(?=$|[\s).,!?:;])/gm, '$1<strong>$2</strong>');
  s = s.replace(/(^|[\s(])_(?!\s)([^_\n]+?)_(?=$|[\s).,!?:;])/gm, '$1<em>$2</em>');
  s = s.replace(/(^|[\s(])~(?!\s)([^~\n]+?)~(?=$|[\s).,!?:;])/gm, '$1<s>$2</s>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
}

function inlineMarkdown(s) {
  const codes = [];
  let out = escapeHtml(s);
  out = out.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0001`; });
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>');
  out = out.replace(/(^|[^*\w])\*(?!\s)([^*]+?)\*(?!\w)/g, '$1<em>$2</em>');
  out = out.replace(/~~([^~]+)~~/g, '<s>$1</s>');
  return out.replace(/\u0001(\d+)\u0001/g, (_, i) => `<code>${codes[+i]}</code>`);
}

const tableCells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
const isTableRow = (line) => /^\s*\|.*\|\s*$/.test(line);

/** Markdown simplificado para as respostas do bot (blocos de código, listas, tabelas...). */
export function renderMarkdown(src) {
  const blocks = [];
  let text = String(src ?? '').replace(/\r\n/g, '\n');
  // blocos de código — inclusive um bloco ainda aberto durante o streaming
  text = text.replace(/```[\w+#.-]*[ \t]*\n?([\s\S]*?)(?:```|$)/g, (_, code) => {
    blocks.push(code.replace(/\n$/, ''));
    return `\n\u0000B${blocks.length - 1}\u0000\n`;
  });

  const lines = text.split('\n');
  let html = '';
  let list = null;
  let para = [];
  const flush = () => { if (para.length) { html += `<p>${para.map(inlineMarkdown).join('<br>')}</p>`; para = []; } };
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  const openList = (tag, attrs = '') => { if (list !== tag) { closeList(); html += `<${tag}${attrs}>`; list = tag; } };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].replace(/\s+$/, '');
    let m;
    if ((m = /^\u0000B(\d+)\u0000$/.exec(line.trim()))) {
      flush(); closeList();
      html += `<pre><code>${escapeHtml(blocks[+m[1]])}</code></pre>`;
      continue;
    }
    if (!line.trim()) { flush(); closeList(); continue; }
    // tabela: | a | b |  seguida de |---|---|
    if (isTableRow(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush(); closeList();
      const head = tableCells(line);
      i += 1;
      let rows = '';
      while (i + 1 < lines.length && isTableRow(lines[i + 1])) {
        i += 1;
        rows += `<tr>${tableCells(lines[i]).map((c) => `<td>${inlineMarkdown(c)}</td>`).join('')}</tr>`;
      }
      html += `<table><thead><tr>${head.map((c) => `<th>${inlineMarkdown(c)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;
      continue;
    }
    if ((m = /^#{1,6}\s+(.*)$/.exec(line))) { flush(); closeList(); html += `<h4>${inlineMarkdown(m[1])}</h4>`; continue; }
    if ((m = /^\s*[-*•]\s+(.*)$/.exec(line))) {
      flush(); openList('ul');
      html += `<li>${inlineMarkdown(m[1])}</li>`;
      continue;
    }
    if ((m = /^\s*(\d+)[.)]\s+(.*)$/.exec(line))) {
      flush(); openList('ol', ` start="${+m[1]}"`);
      html += `<li>${inlineMarkdown(m[2])}</li>`;
      continue;
    }
    if ((m = /^>\s?(.*)$/.exec(line))) { flush(); closeList(); html += `<blockquote>${inlineMarkdown(m[1])}</blockquote>`; continue; }
    closeList();
    para.push(line);
  }
  flush(); closeList();
  return html;
}
