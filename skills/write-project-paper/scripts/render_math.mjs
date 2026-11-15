#!/usr/bin/env node
// 把 HTML 源文件中的 TeX 公式预渲染为内嵌 SVG（MathJax 4，New Computer Modern 字体）。
//
// 用法：node render_math.mjs paper.src.html paper.html
// 行内公式写成 \( ... \)，独立公式写成 \[ ... \]；<code>、<pre>、<script>、<style>、
// <textarea> 中的内容不处理。公式里的 < > & 按 HTML 规则写成 &lt; &gt; &amp;。
//
// MathJax 不随 skill 分发。首次使用前安装到缓存目录（版本固定）：
//   npm install --prefix ~/.cache/write-project-paper/mathjax \
//     @mathjax/src@4.1.3 @mathjax/mathjax-newcm-font@4.1.3
// 也可用环境变量 MATHJAX_HOME 指向另一个已安装上述两个包的目录。

import {createRequire} from 'node:module';
import {existsSync, readFileSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const MATHJAX_VERSION = '4.1.3';
const FONT = 'mathjax-newcm';
const MARKER = `MathJax ${MATHJAX_VERSION} SVG; font ${FONT} (New Computer Modern)`;
const SKIPPED = new Set(['code', 'pre', 'script', 'style', 'textarea']);

function fail(message, code = 1) {
  process.stderr.write(`render_math: ${message}\n`);
  process.exit(code);
}

const [source, target] = process.argv.slice(2);
if (!source || !target) fail('用法：node render_math.mjs <源文件.html> <输出文件.html>', 2);
if (resolve(source) === resolve(target)) fail('输出文件不能覆盖源文件；保留含 TeX 的源文件以便修改后重新渲染', 2);

const home = process.env.MATHJAX_HOME || join(homedir(), '.cache/write-project-paper/mathjax');
const require = createRequire(join(home, 'node_modules', '_'));
let entry;
try {
  entry = require.resolve('@mathjax/src');
  require.resolve('@mathjax/mathjax-newcm-font/package.json');
} catch {
  fail(`未在 ${home} 找到 MathJax。请先运行：\n  npm install --prefix ${home} ` +
       `@mathjax/src@${MATHJAX_VERSION} @mathjax/mathjax-newcm-font@${MATHJAX_VERSION}`, 2);
}
const installed = JSON.parse(readFileSync(require.resolve('@mathjax/src/package.json'), 'utf8')).version;
if (installed !== MATHJAX_VERSION) fail(`MathJax 版本为 ${installed}，需要 ${MATHJAX_VERSION}`, 2);

const imported = await import(pathToFileURL(entry).href);
const MathJax = imported.default ?? imported;
await MathJax.init({
  loader: {load: ['input/tex', 'output/svg', 'adaptors/liteDOM']},
  tex: {packages: {'[+]': ['ams']}},
  output: {font: FONT, fontCache: 'local'},
});
const adaptor = MathJax.startup.adaptor;

const decode = (text) => text
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&');
const escapeAttribute = (text) => text
  .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const errors = [];
let count = 0;

async function render(tex, display) {
  const node = await MathJax.tex2svgPromise(tex, {display});
  let html = adaptor.outerHTML(node);
  if (html.includes('data-mjx-error') || html.includes('merror')) {
    errors.push(tex);
  }
  count += 1;
  const label = escapeAttribute(tex.trim());
  return html.replace('<mjx-container ', `<mjx-container aria-label="${label}" data-tex="${label}" `);
}

const html = readFileSync(source, 'utf8');
if (html.includes('MJX-SVG-styles')) fail('源文件中已有渲染结果；请从含 TeX 的源文件开始渲染', 2);
const tokens = html.split(/(<!--[\s\S]*?-->|<[^>]+>)/);
const skipped = [];
const output = [];
const formula = /\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g;
for (const token of tokens) {
  if (token.startsWith('<')) {
    const tag = /^<\/?\s*([a-zA-Z0-9-]+)/.exec(token);
    if (tag && SKIPPED.has(tag[1].toLowerCase()) && !token.startsWith('<!--')) {
      if (token.startsWith('</')) {
        const index = skipped.lastIndexOf(tag[1].toLowerCase());
        if (index >= 0) skipped.splice(index, 1);
      } else if (!token.endsWith('/>')) {
        skipped.push(tag[1].toLowerCase());
      }
    }
    output.push(token);
    continue;
  }
  if (skipped.length || !formula.test(token)) {
    output.push(token);
    continue;
  }
  formula.lastIndex = 0;
  let last = 0;
  let piece = '';
  for (const match of token.matchAll(formula)) {
    piece += token.slice(last, match.index);
    const display = match[2] !== undefined;
    piece += await render(decode(display ? match[2] : match[1]), display);
    last = match.index + match[0].length;
  }
  output.push(piece + token.slice(last));
}

if (errors.length) fail(`以下 ${errors.length} 个公式有 TeX 错误：\n  ` + errors.join('\n  '));

let result = output.join('');
const style = adaptor.outerHTML(MathJax.svgStylesheet());
const head = `<meta name="math-renderer" content="${MARKER}">\n${style}\n`;
if (!/<\/head>/i.test(result)) fail('源文件缺少 </head>，无法插入公式样式', 2);
result = result.replace(/<\/head>/i, `${head}</head>`);
writeFileSync(target, result);
process.stdout.write(`render_math: ${count} 个公式已渲染（${MARKER}）→ ${target}\n`);
