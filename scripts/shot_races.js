const { chromium } = require('playwright');
(async () => {
  const [,, file, outdir, prefix] = process.argv;
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 });
  await p.goto('file://' + file);
  const els = await p.$$('.race');
  for (let i = 0; i < els.length; i++) {
    const rn = await els[i].$eval('.rn', e => e.textContent.trim()).catch(() => String(i + 1));
    await els[i].screenshot({ path: `${outdir}/${prefix}_${rn}.png` });
  }
  await b.close();
})();
