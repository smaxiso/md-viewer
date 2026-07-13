const katex = require('katex');
try {
  const html = katex.renderToString("\\lambda(y) = g(y)(1 + \\kappa g(y))", { throwOnError: true });
  console.log("Success!");
} catch(e) {
  console.log("KaTeX Error:", e.message);
}
