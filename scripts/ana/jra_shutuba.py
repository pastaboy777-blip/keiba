# -*- coding: utf-8 -*-
"""中央の出馬表を取る。

  python3 scripts/ana/jra_shutuba.py <レースIDの頭10桁> <out.json> [R,R,...]

枠・馬番・馬名・馬ID・性齢・斤量・騎手と、ページ見出しの距離・頭数。
前日は確定オッズが出ていないので、オッズは取れたときだけ入れる。
"""
import json
import os
import re
import subprocess
import sys
import time

HEAD, OUT = sys.argv[1], sys.argv[2]
ONLY = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else list(range(1, 13))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    for i in range(3):
        try:
            b = subprocess.run(['curl', '-sS', '-L', '-A', UA,
                                '-H', 'Accept-Language: ja', '--compressed', u],
                               capture_output=True, timeout=40).stdout
            time.sleep(1.3)
            if len(b) > 40000:
                return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def txt(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).replace('&nbsp;', ' ').strip()


out = {}
if os.path.exists(OUT):
    out = json.load(open(OUT, encoding='utf-8'))
for R in ONLY:
    if str(R) in out:
        continue
    rid = f'{HEAD}{R:02d}'
    p = get(f'https://race.netkeiba.com/race/shutuba.html?race_id={rid}')
    if not p:
        continue
    ttl = re.search(r'<title>([^<]+)</title>', p)
    ttl = ttl.group(1) if ttl else ''
    head = txt(p[:p.find('Shutuba_Table') if 'Shutuba_Table' in p else 20000])
    dm = re.search(r'(芝|ダ)\s*(\d{3,4})m', head)
    ent = []
    for tr in re.findall(r'<tr[^>]*class="[^"]*HorseList[^"]*"[^>]*>(.*?)</tr>', p, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) < 8:
            continue
        g = [txt(x) for x in tds]
        hid = re.search(r'/horse/(\d{10})', tr)
        jk = re.search(r'/jockey/result/recent/\d+/?"[^>]*>([^<]+)<', tr)
        ent.append(dict(waku=g[0], u=g[1], nm=g[3], hid=hid.group(1) if hid else None,
                        sxage=g[4], kin=g[5], jk=jk.group(1).strip() if jk else g[6]))
    if ent:
        out[str(R)] = dict(rid=rid, title=ttl.split('|')[0].strip(),
                           surf=dm.group(1) if dm else '',
                           dist=int(dm.group(2)) if dm else None,
                           n=len(ent), e=ent)
        print(f"  {R:>2}R {out[str(R)]['surf']}{out[str(R)]['dist']}m "
              f"{len(ent)}頭  {out[str(R)]['title']}", flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'書き出し {OUT}  {len(out)}鞍')
