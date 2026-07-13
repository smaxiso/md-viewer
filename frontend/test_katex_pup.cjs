const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage();
  page.on('console', msg => console.log('BROWSER_LOG:', msg.text()));
  page.on('pageerror', err => console.log('BROWSER_ERROR:', err.toString()));
  try {
    await page.goto('http://localhost:8000/?path=docs/unified_supply_chain_strategy.md', { waitUntil: 'domcontentloaded' });
    await new Promise(r => setTimeout(r, 2000));
    const html = await page.evaluate(() => document.querySelector('.markdown-body').innerHTML);
    if (html.includes('$z \\cdot \\sigma$')) {
      console.log("KaTeX DID NOT RENDER formulas!");
    } else {
      console.log("KaTeX rendered formulas successfully!");
    }
  } catch (e) { console.log("Failed:", e); }
  await browser.close();
})();
