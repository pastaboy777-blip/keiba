# -*- coding: utf-8 -*-
"""中央の結果ページから、4角の通過順とラップを取る。

  python3 scripts/ana/jra_corner.py <レースIDの頭10桁> <out.json>

結果表のコーナー通過順の列は空（JSで入る）。
ページ下の「コーナー通過順位」の欄に馬番の並びがあるので、そちらを読む。

括弧の中は同じ順位（CLAUDE.md）。(4,*10,13) は3頭が並走で同着扱い。
一列に並べ直すと、並走の馬に上下がついてしまう。
"""
import json
import os
import re
import subprocess
import sys
import time

HEAD, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    for i in range(3):
        try:
            b = subprocess.run(
                ['curl', '-sS', '-A', UA, '-H', 'Accept-Language: ja',
                 '--compressed', u], capture_output=True, timeout=40).stdout
            time.sleep(1.2)
            if len(b) > 20000:
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def corner_rank(s, n):
    """コーナーの並びを {馬番: 正規化位置} にする。括弧の中は同じ順位。"""
    groups, buf, i = [], [], 0
    while i < len(s):
        c = s[i]
        if c == '(':
            j = s.find(')', i)
            g = [int(x) for x in re.findall(r'\d+', s[i:j + 1])]
            if g:
                groups.append(g)
            i = j + 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            groups.append([int(s[i:j])])
            i = j
        else:
            i += 1
    out, rank = {}, 1
    for g in groups:
        for u in g:
            out[u] = rank          # 並走は同じ順位
        rank += len(g)             # 次の順位は頭数ぶん飛ばす
    return {u: ((r - 1) / (n - 1) if n > 1 else .5) for u, r in out.items()}


out = {}
if os.path.exists(OUT):                      # 取れた鞍は残して、欠けだけ拾い直す
    out = json.load(open(OUT, encoding='utf-8'))
    out = {k: v for k, v in out.items() if v.get('corner_raw')}
for R in range(1, 13):
    if str(R) in out:
        continue
    rid = f'{HEAD}{R:02d}'
    p = get(f'https://race.netkeiba.com/race/result.html?race_id={rid}')
    if not p:
        continue
    rows = re.findall(r'<tr[^>]*class="[^"]*HorseList[^"]*"[^>]*>(.*?)</tr>',
                      p, re.S)
    n = len(rows)
    if not n:
        continue
    i = p.find('コーナー通過順位')
    seg = re.sub(r'\s+', '', re.sub(r'<[^>]+>', '|', p[i:i + 1600])) if i > 0 else ''
    # 「|3|コーナー|…|4|コーナー|…」の、最後のコーナーの並びを取る
    last = ''
    if seg:
        tail = seg.split('コーナー通過順位の見方')[0]
        marks = [m.end() for m in re.finditer(r'\|\d\|コーナー\|', tail)]
        if marks:
            last = re.sub(r'[^0-9,\-=()*]', '', tail[marks[-1]:])
    lap = []
    j = p.find('ラップタイム')
    if j > 0:
        t = re.sub(r'\s+', '', re.sub(r'<[^>]+>', '|', p[j:j + 1800]))
        lap = re.findall(r'\|(\d{1,2}\.\d)\|', t)
    pace = re.search(r'ペース:\|?([HMS])', re.sub(r'\s+', '', re.sub(r'<[^>]+>', '|', p[j:j + 400]))) if j > 0 else None
    out[str(R)] = dict(rid=rid, n=n, corner_raw=last,
                       c4=corner_rank(last, n) if last else {},
                       lap=lap, pace=pace.group(1) if pace else '')
    print(f'  {R:>2}R {n}頭  4角 {last[:54]}', flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'書き出し {OUT}  {len(out)}鞍')
