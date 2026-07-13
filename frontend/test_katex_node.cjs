const renderMathInElement = require('katex/contrib/auto-render');
const katex = require('katex');
const fs = require('fs');
const jsdom = require("jsdom");
const { JSDOM } = jsdom;

const html = fs.readFileSync('/home/sumit/workspace/smaxiso/md-viewer/backend/test_html.html', 'utf-8');
const dom = new JSDOM(html);
const document = dom.window.document;

try {
  renderMathInElement(document.body, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
      { left: '\\(', right: '\\)', display: false },
      { left: '\\[', right: '\\]', display: true },
    ],
    throwOnError: false,
  });
  console.log("KaTeX rendered successfully!");
} catch (e) {
  console.error("KaTeX failed:", e);
}
