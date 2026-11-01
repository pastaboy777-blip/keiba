# -*- coding: utf-8 -*-
"""通過順位を、記号を落とさずに取り直す。

  python3 scripts/ana/fetch_nankan_corners.py <nankan.jsonl> <out.jsonl>

これまで `re.findall(r'\\d+')` で数字だけ抜いていたので、記号を捨てていた。
記号には着差が入っている。

  ( )  ほぼ横並び
  ,    1馬身以内
  -    1〜2馬身
  =    大きくあいた

先頭の通過時計はハロンタイムの累積で出せるので、記号から各馬の着差を
読めば、中間の通過タイムを推定で作れる。米国の区間タイムも同じ作り方
（公式に測るのは先頭だけで、各馬は着差から計算している）。

取得済みの rid は飛ばすので、止めても続きから走る。1.2秒あける。
"""
import json, os, re, sys, time, urllib.request

SRC, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
LAB = (('１角', 'c1s'), ('２角', 'c2s'), ('３角', 'c3s'), ('４角', 'c4s'))


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.2)
            for enc in ('euc_jp', 'utf-8', 'cp932'):
                try:
                    return b.decode(enc)
                except Exception:
                    pass
            return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3 * (i + 1))
    return None


ids = []
for l in open(SRC, encoding='utf-8'):
    r = json.loads(l)
    if r.get('e'):
        ids.append(r['rid'])
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
    p = get(f'https://keiba.rakuten.co.jp/race_performance/list/RACEID/{rid}')
    if not p:
        continue
    t = re.sub(r'<[^>]+>', '\n', p).replace('&nbsp;', ' ')
    L = [x.strip() for x in t.split('\n') if x.strip()]
    d = {'rid': rid}
    j = next((j for j, x in enumerate(L) if 'コーナー通過順位' in x), None)
    if j is not None:
        seg = L[j:j + 14]
        for k, key in LAB:
            m = next((m for m, x in enumerate(seg) if x == k), None)
            if m is not None and m + 1 < len(seg):
                s = seg[m + 1]
                if re.match(r'^[\d(),=\-\s]+$', s):
                    d[key] = s.replace(' ', '')
    f.write(json.dumps(d, ensure_ascii=False) + '\n')
    if n % 100 == 0:
        print(f'  {n}/{len(todo)}', flush=True)
print('完了', flush=True)
