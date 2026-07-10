const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('BROWSER_LOG:', msg.text()));
  
  try {
    await page.goto('http://localhost:8000/?path=docs/buying/unified_strategy.md', { waitUntil: 'domcontentloaded' });
    await new Promise(r => setTimeout(r, 2000));
    const html = await page.evaluate(() => document.querySelector('.markdown-body').innerHTML);
    console.log("HTML_SNIPPET:", html.substring(1500, 2500));
  } catch (e) {
    console.log("Failed:", e);
  }
  
  await browser.close();
})();
