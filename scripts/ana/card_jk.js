// 楽天の出馬表（race_card）から 騎手・調教師・枠・斤量 を**表のセルごと**読む。
//   node card_jk.js <base16> <R...>      例: node card_jk.js 2026111121350903 1 2 3 4 5
//   OUT=... で出力先を指定（既定 card_jk.json）
//
// なぜ要るか … オッズ頁（tanfuku）は発走の数時間前まで開かないので、前夜は騎手が取れない。
//   出馬表には「騎手名」「調教師名」の列があるので、そこから取る。
//   騎手は内外（jk_soto.json）に、調教師は2頭出しの判定（CLAUDE.md ルール24）に使う。
//
// ★ innerText を正規表現で切らないこと。2026-11-09 に列がずれて馬名とオッズの対応が
//   崩れた（rk_odds.js の頭にも同じ注意がある）。<td> を順番に読む。
const { chromium } = require('playwright');
(async () => {
  const [base, ...rs] = process.argv.slice(2);
  if (!base) { console.log('使い方: node card_jk.js <base16> <R...>'); process.exit(1); }
  const b = await chromium.launch();
  const p = await b.newPage();
  const all = {};
  for (const R of rs) {
    const rid = base + String(R).padStart(2, '0');
    await p.goto('https://keiba.rakuten.co.jp/race_card/list/RACEID/' + rid,
                 { waitUntil: 'networkidle', timeout: 45000 });
    const rows = await p.$$eval('table tr', trs => trs.map(tr =>
      Array.from(tr.querySelectorAll('td,th')).map(td => td.innerText.replace(/\s+/g, ' ').trim())));
    const head = rows.find(r => r.includes('馬名') && r.includes('騎手名'));
    if (!head) { console.log(R + 'R 表が見つかりません'); continue; }
    const ix = n => head.indexOf(n);
    const out = [];
    for (const r of rows) {
      if (r.length !== head.length || r === head) continue;
      const ub = parseInt(r[ix('馬番')], 10);
      if (!ub) continue;
      // 「騎手名」のセルは "▲西優哉 【勝率】…" のような形。先頭の名前だけ取る
      const jkRaw = (r[ix('騎手名')] || '').split(' ')[0];
      const trRaw = (r[ix('調教師名')] || '').split(' ')[0];
      const kin = ((r[ix('負担重量')] || '').match(/([\d.]+)/) || [])[1];
      out.push({ ub, waku: parseInt(r[ix('枠番')], 10), name: r[ix('馬名')],
                 jk: jkRaw, tr: trRaw, kin: kin ? +kin : null });
    }
    all[R] = out;
    console.log('=== ' + R + 'R  ' + out.length + '頭 ===');
    out.forEach(o => console.log('  ' + String(o.waku) + '枠 ' + String(o.ub).padStart(2) + ' ' +
      o.name.padEnd(18, '　').slice(0, 18) + ' 斤' + o.kin + '  ' + o.jk + '  ' + o.tr));
    console.log('');
  }
  require('fs').writeFileSync(process.env.OUT || 'card_jk.json', JSON.stringify(all, null, 1));
  await b.close();
})();
