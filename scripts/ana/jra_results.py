# -*- coding: utf-8 -*-
"""中央競馬の1日ぶんの結果を取る。芝・ダートを分けて見るため。

  python3 scripts/ana/jra_results.py 20261024 <out.json>

race.netkeiba.com の結果ページから、距離・馬場・ラップ・前後半と
各馬の着順・人気・上り3F・通過順・馬体重を取る。
"""
import json, re, sys, time, urllib.request

DATE, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
JYO = {'01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
       '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'}


def get(u):
    b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}),
                               timeout=30).read()
    time.sleep(1.2)
    return b.decode('utf-8', 'replace')


def clean(h):
    h = re.sub(r'<[^>]+>', ' ', h).replace('&nbsp;', ' ').replace('&amp;', '&')
    return re.sub(r'\s+', ' ', h).strip()


t = get(f'https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={DATE}')
ids = sorted(set(re.findall(r'race_id=(\d{12})', t)))
print(f'{DATE}  {len(ids)}鞍', flush=True)

out = {}
for rid in ids:
    try:
        p = get(f'https://race.netkeiba.com/race/result.html?race_id={rid}')
        nm = clean((re.findall(r'<div class="RaceName">(.*?)</div>', p, re.S) or [''])[0])
        d1 = clean((re.findall(r'<div class="RaceData01">(.*?)</div>', p, re.S) or [''])[0])
        d2 = clean((re.findall(r'<div class="RaceData02">(.*?)</div>', p, re.S) or [''])[0])
        m = re.search(r'(芝|ダ|障)\s*(\d{3,4})m', d1)
        surf = {'芝': '芝', 'ダ': 'ダート', '障': '障害'}.get(m.group(1)) if m else None
        dist = int(m.group(2)) if m else None
        baba = (re.search(r'(良|稍重|重|不良)', d1.split('/')[-1]) or
                re.search(r'馬場:(\S+)', d1))
        baba = baba.group(1) if baba else ''
        lap = re.findall(r'<td[^>]*>([\d]{1,2}\.\d)</td>', p)
        hr = re.search(r'ハロンタイム.*?</table>', p, re.S)
        lap = re.findall(r'>(\d{1,2}\.\d)<', hr.group(0)) if hr else []
        pc = re.search(r'ペース.*?</table>', p, re.S)
        pace = clean(pc.group(0))[:60] if pc else ''
        rows = []
        for r in re.findall(r'<tr class="HorseList">(.*?)</tr>', p, re.S):
            cs = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)]
            hid = re.search(r'/horse/(\d{10})', r)
            if len(cs) < 14:
                continue
            rows.append(dict(f=cs[0], waku=cs[1], u=cs[2], nm=cs[3], sxage=cs[4],
                             kin=cs[5], jk=cs[6], tm=cs[7], mgn=cs[8], pop=cs[9],
                             odds=cs[10], ag=cs[11], c=cs[12], tr=cs[13],
                             wt=cs[14] if len(cs) > 14 else '',
                             id=hid.group(1) if hid else None))
        out[rid] = dict(ba=JYO.get(rid[4:6], rid[4:6]), R=int(rid[10:12]), name=nm,
                        surf=surf, dist=dist, baba=baba, d1=d1, d2=d2,
                        lap=lap, pace=pace, e=rows)
        print(f"  {out[rid]['ba']}{out[rid]['R']:>2}R {surf}{dist} {baba} {len(rows)}頭 {nm[:18]}", flush=True)
    except Exception as e:
        print(f'  NG {rid} {e}', flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('書き出し', OUT)
