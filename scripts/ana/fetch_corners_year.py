# -*- coding: utf-8 -*-
"""楽天の成績ページからコーナー通過順位を1年ぶん取る。

  python3 scripts/ana/fetch_corners_year.py <runs.jsonl> <out.jsonl>

コーナリングのうまさを「3角→4角で位置を上げたか」で測るための材料。
取得済みの rid は飛ばすので、止めても続きから走る。有料サイトではないが
1.2秒間隔を守る。
"""
import json, os, re, sys, time, urllib.request

RUNS, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.2)
            try:
                return b.decode('euc_jp')
            except Exception:
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3 * (i + 1))
    return None


ids = []
for l in open(RUNS, encoding='utf-8'):
    r = json.loads(l)
    if r.get('dist') and r.get('e'):
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
        for k, lab in (('１角', 'c1'), ('２角', 'c2'), ('３角', 'c3'), ('４角', 'c4')):
            m = next((m for m, x in enumerate(seg) if x == k), None)
            if m is not None and m + 1 < len(seg):
                d[lab] = [int(x) for x in re.findall(r'\d+', seg[m + 1])]
    i = next((i for i, x in enumerate(L) if x == 'ハロンタイム'), None)
    if i is not None and i + 1 < len(L):
        d['lap'] = [float(x) for x in re.findall(r'\d{1,2}\.\d', L[i + 1])]
    f.write(json.dumps(d, ensure_ascii=False) + '\n')
    if n % 50 == 0:
        print(f'  {n}/{len(todo)}', flush=True)
print('完了', flush=True)
