# -*- coding: utf-8 -*-
"""結果JSONの馬IDから、父と母父を取る。

  python3 scripts/ana/jra_sire.py notes/.../2026030301.json out.jsonl

db.netkeiba は urllib だと 400 が返る。curl で取る（1.4秒あける）。
取得済みの馬IDは飛ばすので、止めても続きから走る。
"""
import json
import os
import re
import subprocess
import sys
import time

SRC, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    for i in range(3):
        try:
            b = subprocess.run(['curl', '-sS', '-L', '-A', UA,
                                '-H', 'Accept-Language: ja', '--compressed', u],
                               capture_output=True, timeout=40).stdout
            time.sleep(1.4)
            if len(b) > 8000:
                return b.decode('euc_jp', 'replace')
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def clean(s):
    s = re.sub(r'<[^>]+>', '', s).replace('&nbsp;', ' ')
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\[血統\]|\[産駒\]', ' ', s)
    s = re.sub(r'\b(1[6-9]|20)\d\d\b.*$', '', s)      # 生年から後ろを落とす
    s = re.sub(r'\s*\([^)]{1,8}\)\s*$', '', s)
    return s.strip()


D = json.load(open(SRC, encoding='utf-8'))
want = {}
for k, r in D.items():
    for e in r['e']:
        if e.get('hid'):
            want[e['hid']] = (k, e['nm'], e.get('f'), e.get('pop'))

done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            done.add(json.loads(l)['hid'])
        except Exception:
            pass
todo = [h for h in want if h not in done]
print(f'{len(want)}頭 / 取得済み {len(done)} / これから {len(todo)}', flush=True)

f = open(OUT, 'a', encoding='utf-8', buffering=1)
for n, hid in enumerate(todo, 1):
    p = get(f'https://db.netkeiba.com/horse/ped/{hid}/')
    if not p:
        continue
    # 5代血統表は62セル。文書順の先頭が父、32番目が母。母父は母の次の行の先頭。
    cells = [clean(x) for x in re.findall(r'<td[^>]*class="[^"]*b_[^"]*"[^>]*>(.*?)</td>',
                                          p, re.S)]
    if len(cells) < 62:
        cells = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', p, re.S)]
    sire = cells[0] if cells else ''
    dam = cells[31] if len(cells) > 31 else ''
    damsire = cells[32] if len(cells) > 32 else ''
    k, nm, fin, pop = want[hid]
    f.write(json.dumps(dict(hid=hid, R=k, nm=nm, f=fin, pop=pop,
                            sire=sire, dam=dam, damsire=damsire),
                       ensure_ascii=False) + '\n')
    if n % 20 == 0:
        print(f'  {n}/{len(todo)}  {nm} 父{sire} 母父{damsire}', flush=True)
print('完了', flush=True)
