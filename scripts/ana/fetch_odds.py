# -*- coding: utf-8 -*-
"""全馬の単勝・複勝オッズを取る。

  python3 scripts/ana/fetch_odds.py <list.jsonl> <out.jsonl>

これまで持っていたのは払戻（勝ち馬の単勝、3着までの複勝）だけで、
出走全馬の値段は持っていなかった。市場の「形」を見るには全馬が要る。

楽天のオッズページ（odds/tanfuku）に全馬ぶん並んでいる。
  馬番 馬名 性齢 斤量 騎手 厩舎 連対時馬体重 馬体重 増減 単勝 複勝下 - 複勝上 人気

取得済みの rid は飛ばすので、止めても続きから走る。1.2秒あける。
"""
import json, os, re, sys, time, urllib.request

SRC, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
NAME = re.compile(r'^[ァ-ヶー]{2,}$')


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.2)
            return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3 * (i + 1))
    return None


ids = [json.loads(l)['rid'] for l in open(SRC, encoding='utf-8')]
done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            done.add(json.loads(l)['rid'])
        except Exception:
            pass
todo = [x for x in ids if x not in done]
print(f'{len(ids)}鞍 / 取得済み {len(done)} / これから {len(todo)}', flush=True)

f = open(OUT, 'a', encoding='utf-8', buffering=1)
for n, rid in enumerate(todo, 1):
    p = get(f'https://keiba.rakuten.co.jp/odds/tanfuku/RACEID/{rid}')
    if not p:
        continue
    L = [x.strip() for x in
         re.sub(r'<[^>]+>', '\n', p).replace('&nbsp;', ' ').split('\n')
         if x.strip()]
    out = []
    for i, x in enumerate(L):
        m = re.match(r'^(\d+)番人気$', x)
        if not m or i < 5:
            continue
        try:
            tan, fl, fh = float(L[i - 4]), float(L[i - 3]), float(L[i - 1])
        except (ValueError, IndexError):
            continue
        # 馬名はさらに前。カタカナだけの行をさかのぼって探す
        nm = ''
        for j in range(i - 5, max(0, i - 20), -1):
            if NAME.match(L[j]):
                nm = L[j]
                break
        out.append(dict(nm=nm, tan=tan, fl=fl, fh=fh, pop=int(m.group(1))))
    if out:
        f.write(json.dumps({'rid': rid, 'o': out}, ensure_ascii=False) + '\n')
    if n % 100 == 0:
        print(f'  {n}/{len(todo)}  直近 {len(out)}頭', flush=True)
print('完了', flush=True)
