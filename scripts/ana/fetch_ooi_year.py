# -*- coding: utf-8 -*-
"""楽天競馬の成績ページから、ある場の1年ぶんの着順表を取る。

  python3 scripts/ana/fetch_ooi_year.py <days.json> <out.jsonl>

days.json は [[YYYYMMDD, [RACEID,...]], ...]。
成績ページは13列（着順・枠・馬番・馬名・性齢/毛色・負担重量・馬体重増減・
騎手・タイム・着差・推定上がり・調教師・人気）で、出馬表とは並びが違う。
取得済みの RACEID は飛ばすので、止めても続きから走る。
"""
import json, os, re, sys, time, urllib.request

DAYS, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
SX = re.compile(r'^(牡|牝|セ)\d')


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.0)
            try:
                return b.decode('euc_jp')
            except Exception:
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def clean(h):
    h = re.sub(r'<[^>]+>', '\n', h).replace('&nbsp;', ' ')
    return [x.strip() for x in h.split('\n') if x.strip()]


days = json.load(open(DAYS, encoding='utf-8'))
done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            done.add(json.loads(l)['rid'])
        except Exception:
            pass
todo = [(y, r) for y, ids in days for r in ids if r not in done]
print(f'{len(days)}日 / 取得済み {len(done)} / これから {len(todo)}鞍', flush=True)

f = open(OUT, 'a', encoding='utf-8', buffering=1)
tot = 0
for ymd, rid in todo:
    p = get(f'https://keiba.rakuten.co.jp/race_performance/list/RACEID/{rid}')
    if not p:
        continue
    head = ' '.join(clean(p[:9000])[:60])
    dm = re.search(r'(\d{3,4})\s*m', head)
    dist = int(dm.group(1)) if dm else None
    bm = re.search(r'(良|稍重|重|不良)', head)
    rows = []
    for tb in re.findall(r'<table.*?</table>', p, re.S):
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            cs = [clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
            if len(cs) < 13:
                continue
            k = next((i for i, c in enumerate(cs)
                      if c and SX.match(c[0].replace(' ', ''))), None)
            if k != 4:                      # 着順,枠,馬番,馬名,性齢 の並びだけ採る
                continue
            g = lambda i: (cs[i][0] if i < len(cs) and cs[i] else '')
            rows.append(dict(f=g(0), waku=g(1), u=g(2), nm=g(3), sx=g(4),
                             kin=g(5), wt=g(6),
                             dw=(cs[6][1] if len(cs) > 6 and len(cs[6]) > 1 else ''),
                             jk=g(7), tm=g(8), mgn=g(9), ag=g(10), tr=g(11), pop=g(12)))
        if rows:
            break
    f.write(json.dumps(dict(rid=rid, ymd=ymd, dist=dist,
                            baba=bm.group(1) if bm else '', n=len(rows),
                            e=rows), ensure_ascii=False) + '\n')
    tot += 1
    if tot % 50 == 0:
        print(f'  {tot}/{len(todo)}鞍 ({ymd})', flush=True)
print('完了', tot, '鞍', flush=True)
