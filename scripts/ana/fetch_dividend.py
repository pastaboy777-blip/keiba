# -*- coding: utf-8 -*-
"""楽天競馬の払戻金を1日ぶん取る。

  python3 scripts/ana/fetch_dividend.py <どれか1鞍のRACEID> <out.json>

/race_dividend/list/RACEID/{18桁} は、その日その場の全レースが
1ページに入っている（新しいRから古いRの順）。各レースは
  「単勝 | 5 | 250 円 | 3番人気 | 馬単 | …」
の形で、複勝とワイドだけは「買い目を3つ並べてから金額を3つ並べる」。
"""
import json, re, sys, time, urllib.request

RID, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
KIND = ('単勝', '複勝', '枠複', '枠単', '馬複', 'ワイド', '馬単', '三連複', '三連単')

b = urllib.request.urlopen(urllib.request.Request(
    f'https://keiba.rakuten.co.jp/race_dividend/list/RACEID/{RID}',
    headers={'User-Agent': UA}), timeout=30).read()
try:
    p = b.decode('euc_jp')
except Exception:
    p = b.decode('utf-8', 'replace')
t = re.sub(r'<[^>]+>', '\n', p).replace('&nbsp;', ' ')
L = [x.strip() for x in t.split('\n') if x.strip()]

heads = [(i, x) for i, x in enumerate(L) if re.match(r'^\d+R\s', x)]
out = {}
for k, (i, title) in enumerate(heads):
    j = heads[k + 1][0] if k + 1 < len(heads) else len(L)
    seg = L[i:j]
    R = re.match(r'^(\d+)R', title).group(1)
    d = {}
    pos = [(n, x) for n, x in enumerate(seg) if x in KIND]
    for n, (idx, kind) in enumerate(pos):
        end = pos[n + 1][0] if n + 1 < len(pos) else len(seg)
        body = seg[idx + 1:end]
        buys = [x for x in body if re.match(r'^[\d]+(-[\d]+)*$', x)]
        yens = [int(x[:-1].replace(',', '').strip())
                for x in body if re.match(r'^[\d,]+\s*円$', x)]
        if buys and yens and kind not in d:
            d[kind] = list(zip(buys, yens))
    out[R] = dict(title=title, d=d)
    s = '／'.join(f"{k_}{v[0][0]} {v[0][1]:,}" for k_, v in d.items()
                  if k_ in ('単勝', '馬複', '三連複'))
    print(f'{R:>3}R  {s}', flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('書き出し', OUT)
