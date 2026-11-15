// 楽天の単勝ページを**表のセルごと**読む。オッズ・人気・騎手・馬体重・増減・斤量。
//   node rk_odds.js <base16> <R...>      例: node rk_odds.js 2026110921350901 10 11 12
//
// ★ 2026-11-09 にここで間違えた。
//   ページ下部の「みんなの予想まとめ」を innerText で正規表現にかけたところ、
//   列がずれて**馬名とオッズの対応が崩れた**（10Rで1人気と6人気が入れ替わって出た）。
//   表の <td> を順番に読めばずれない。**innerText を正規表現で切らないこと。**
const { chromium } = require('playwright');
(async () => {
  const [base, ...rs] = process.argv.slice(2);
  if (!base) { console.log('使い方: node rk_odds.js <base16> <R...>'); process.exit(1); }
  const b = await chromium.launch();
  const p = await b.newPage();
  const all = {};
  for (const R of rs) {
    const rid = base + String(R).padStart(2, '0');
    await p.goto('https://keiba.rakuten.co.jp/odds/tanfuku/RACEID/' + rid,
                 { waitUntil: 'networkidle', timeout: 45000 });
    const rows = await p.$$eval('table tr', trs => trs.map(tr =>
      Array.from(tr.querySelectorAll('td,th')).map(td => td.innerText.replace(/\s+/g, ' ').trim())));
    const head = rows.find(r => r.includes('単勝オッズ'));
    if (!head) { console.log(R + 'R 表が見つかりません'); continue; }
    const ix = n => head.indexOf(n);
    const out = [];
    for (const r of rows) {
      if (r.length !== head.length || r === head) continue;
      const ub = parseInt(r[ix('馬番')], 10);
      if (!ub) continue;
      const sex = r[ix('性齢/毛色負担重量')] || '';
      const kin = (sex.match(/([\d.]+)$/) || [])[1];
      const jk = (r[ix('騎手名調教師名')] || '').split(' (')[0];
      const wz = (r[ix('馬体重増減')] || '').match(/^(\d{3})([+\-±]\d+)?$/) || [];
      out.push({ ub, waku: parseInt(r[ix('枠番')], 10), name: r[ix('馬名')],
                 kin: kin ? +kin : null, jk,
                 w: wz[1] ? +wz[1] : null, dw: wz[2] || null,
                 odds: parseFloat(r[ix('単勝オッズ')]),
                 nin: parseInt(r[ix('人気')], 10) });
    }
    all[R] = out;
    const ws = out.filter(o => o.w).map(o => o.w);
    const avg = ws.length ? ws.reduce((a, c) => a + c, 0) / ws.length : null;
    console.log('=== ' + R + 'R  ' + out.length + '頭' +
                (avg ? '  馬体重の平均 ' + avg.toFixed(0) + 'kg' : '') + ' ===');
    out.slice().sort((a, c) => a.nin - c.nin).forEach(o =>
      console.log('  ' + String(o.nin).padStart(2) + '人気 ' + String(o.odds).padStart(6) + '倍  ' +
        String(o.waku) + '枠 ' + String(o.ub).padStart(2) + ' ' +
        o.name.padEnd(20, '　').slice(0, 20) + ' 斤' + o.kin +
        '  ' + (o.w ? o.w + (o.dw || '') + (avg ? ' (平均比' + (o.w - avg > 0 ? '+' : '') + (o.w - avg).toFixed(0) + ')' : '') : '―') +
        '  ' + o.jk));
    console.log('');
  }
  require('fs').writeFileSync(process.env.OUT || 'odds.json', JSON.stringify(all, null, 1));
  await b.close();
})();
