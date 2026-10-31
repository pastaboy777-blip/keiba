# -*- coding: utf-8 -*-
"""中央の1日1場ぶんの結果を取る。

  python3 scripts/ana/jra_day.py <レースIDの頭10桁> <out.json>

例 2026080410 なら 2026年・京都(08)・4回・10日目。
netkeiba の結果ページから 着順・枠・馬番・馬名・性齢・斤量・騎手・
タイム・着差・人気・オッズ・上り3F・馬体重 と、馬のIDを取る。
表の列数が揃っているので、行ごとに素直に拾えばよい。
"""
import json, re, sys, time, urllib.request

HEAD, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.0)
            for enc in ('euc_jp', 'utf-8', 'cp932'):
                try:
                    return b.decode(enc)
                except Exception:
                    pass
            return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def cell(td):
    """セルの中身を、馬のIDごと取り出す"""
    hid = re.search(r'/horse/(\w+)', td)
    t = re.sub(r'<[^>]+>', ' ', td)
    t = re.sub(r'\s+', ' ', t).replace('&nbsp;', ' ').strip()
    return t, (hid.group(1) if hid else None)


out = {}
for R in range(1, 13):
    rid = f'{HEAD}{R:02d}'
    p = get(f'https://race.netkeiba.com/race/result.html?race_id={rid}')
    if not p:
        continue
    ttl = re.search(r'<title>([^<]+)</title>', p)
    ttl = ttl.group(1) if ttl else ''
    if 'netkeiba' not in ttl or '|' not in ttl or '結果' not in ttl:
        continue
    head = re.sub(r'<[^>]+>', ' ', p[:p.find('ResultTableWrap') if
                                      'ResultTableWrap' in p else 20000])
    head = re.sub(r'\s+', ' ', head)
    dm = re.search(r'(芝|ダ)\s*(\d{3,4})m', head)
    bm = re.search(r'(良|稍重|重|不良)', head)
    rows = []
    for tr in re.findall(r'<tr[^>]*class="[^"]*HorseList[^"]*"[^>]*>(.*?)</tr>',
                         p, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) < 13:
            continue
        v = [cell(x) for x in tds]
        g = lambda i: v[i][0] if i < len(v) else ''
        hid = next((h for _, h in v if h), None)
        rows.append(dict(f=g(0), waku=g(1), u=g(2), nm=g(3), sxage=g(4),
                         kin=g(5), jk=g(6), tm=g(7), mgn=g(8), pop=g(9),
                         odds=g(10), ag=g(11), pass_=g(12),
                         wt=g(14) if len(v) > 14 else '', hid=hid))
    if rows:
        out[str(R)] = dict(rid=rid, title=ttl.split('|')[0].strip(),
                           date=(ttl.split('|')[1].split('R')[0].strip()
                                 if '|' in ttl else ''),
                           surf=dm.group(1) if dm else '',
                           dist=int(dm.group(2)) if dm else None,
                           baba=bm.group(1) if bm else '', n=len(rows), e=rows)
        print(f"  {R:>2}R {out[str(R)]['surf']}{out[str(R)]['dist']}m "
              f"{out[str(R)]['baba']} {len(rows)}頭  "
              f"1着 {rows[0]['nm']}({rows[0]['pop']}人)", flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'書き出し {OUT}  {len(out)}鞍')
