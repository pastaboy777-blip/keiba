# -*- coding: utf-8 -*-
"""出走馬の過去走から「ふだんどこにいて、終いがどれだけ速いか」を出す。

  python3 scripts/ana/jra_horse_pos.py <shutuba.json> <out.jsonl> [R,R,...]

土曜の福島で穴になったのは「4角で後ろ × 上がり上位」だった。
前日に当てられるのは、その馬がふだんどこを走るか。

  ふだんの4角位置 ＝ (最終コーナーの順位 − 1) ÷ (頭数 − 1)   0が先頭
  終いの速さ      ＝ 自身の上り3F − そのレースの後半3F        マイナスほど速い

レースの後半3Fは、netkeiba の成績表の「ペース」欄（前半3F-後半3F）の右側。
馬の上りと同じ物差しなので、そのまま引ける。全馬の上りを取らなくてよい。

通過順は "9-8" や "14-14-13-12" の形。最後の数字が4角。
"""
import json
import os
import re
import subprocess
import sys
import time

SRC, OUT = sys.argv[1], sys.argv[2]
ONLY = sys.argv[3].split(',') if len(sys.argv) > 3 else None
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    for i in range(3):
        try:
            b = subprocess.run(['curl', '-sS', '-L', '-A', UA,
                                '-H', 'Accept-Language: ja', '--compressed', u],
                               capture_output=True, timeout=40).stdout
            time.sleep(1.3)
            if len(b) > 20000:
                return b.decode('euc_jp', 'replace')
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def txt(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).replace('&nbsp;', ' ').strip()


S = json.load(open(SRC, encoding='utf-8'))
want = []
for k in sorted(S, key=int):
    if ONLY and k not in ONLY:
        continue
    for e in S[k]['e']:
        if e.get('hid'):
            want.append((k, e))

done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            done.add(json.loads(l)['hid'])
        except Exception:
            pass
todo = [(k, e) for k, e in want if e['hid'] not in done]
print(f'{len(want)}頭 / 取得済み {len(done)} / これから {len(todo)}', flush=True)

f = open(OUT, 'a', encoding='utf-8', buffering=1)
for n, (k, e) in enumerate(todo, 1):
    p = get(f'https://db.netkeiba.com/horse/result/{e["hid"]}/')
    if not p:
        continue
    runs = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', p, re.S):
        g = [txt(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
        if len(g) < 29 or not re.match(r'^20\d\d/', g[0]):
            continue
        try:
            n_head = int(g[6])
        except ValueError:
            continue
        ps = [int(x) for x in re.findall(r'\d+', g[25])]
        pace = re.match(r'^([\d.]+)-([\d.]+)$', g[26] or '')
        try:
            ag = float(g[27])
        except ValueError:
            ag = None
        runs.append(dict(
            date=g[0], ba=g[1], n=n_head, u=g[8], pop=g[10], f=g[11],
            dist=g[14], baba=g[16], tm=g[18],
            c4=((ps[-1] - 1) / (n_head - 1)) if ps and n_head > 1 else None,
            c4r=ps[-1] if ps else None, ag=ag,
            f3=float(pace.group(1)) if pace else None,
            l3=float(pace.group(2)) if pace else None,
            gap=(ag - float(pace.group(2))) if (pace and ag is not None) else None))
    f.write(json.dumps(dict(R=k, u=e['u'], waku=e['waku'], nm=e['nm'], hid=e['hid'],
                            sxage=e['sxage'], kin=e['kin'], jk=e['jk'], runs=runs),
                       ensure_ascii=False) + '\n')
    if n % 16 == 0:
        print(f'  {n}/{len(todo)}  {e["nm"]} {len(runs)}走', flush=True)
print('完了', flush=True)
