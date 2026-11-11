/* Testes da formatação de mensagens da interface (funções puras, node --test). */
import assert from 'node:assert/strict';
import test from 'node:test';
import { formatWhats, renderMarkdown } from '../renderer/js/format.js';
import { escapeHtml, initials, modelOf } from '../renderer/js/utils.js';

test('formatação estilo WhatsApp escapa HTML antes de formatar', () => {
  assert.equal(formatWhats('*oi* <b>x</b>'), '<strong>oi</strong> &lt;b&gt;x&lt;/b&gt;');
  assert.equal(formatWhats('use `a*b*c` aqui'), 'use <code>a*b*c</code> aqui');
  assert.equal(formatWhats('_it_ e ~risc~'), '<em>it</em> e <s>risc</s>');
});

test('markdown do bot: listas, código e tabela', () => {
  assert.equal(renderMarkdown('- um\n- dois'), '<ul><li>um</li><li>dois</li></ul>');
  assert.equal(renderMarkdown('```py\nprint("<x>")\n```'), '<pre><code>print(&quot;&lt;x&gt;&quot;)</code></pre>');
  assert.match(renderMarkdown('| A | B |\n|---|---|\n| 1 | 2 |'), /<th>A<\/th><th>B<\/th>.*<td>1<\/td><td>2<\/td>/);
});

test('bloco de código ainda aberto (streaming) é exibido', () => {
  assert.equal(renderMarkdown('```\nparcial'), '<pre><code>parcial</code></pre>');
});

test('utilitários', () => {
  assert.equal(escapeHtml(`"'&`), '&quot;&#39;&amp;');
  assert.equal(initials('ana_maria'), 'AM');
  assert.equal(modelOf({ client: 'sd-bot/qwen3.5:4b' }), 'qwen3.5:4b');
});
