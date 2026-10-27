# -*- coding: utf-8 -*-
"""楽天競馬の成績ページからラップと通過順位を1日ぶん取る。

  python3 scripts/ana/fetch_laps_rakuten.py <card.json> <out.json>

成績ページの下のほうに
  ハロンタイム | 12.4-11.2-11.7-12.7-12.8-13.6 | 上がり | 4F 50.8 - 3F 39.1
  コーナー通過順位 | ３角 | 7,6,9,… | ４角 | 7-6,9-…
が入っている。
33ラップ＝「残り6〜3F」−「レース上がり3F」。マイナスが大きいほど前が速い
持久戦、0に近いほど瞬発戦（作者の線引きは1秒）。
"""
import json, re, sys, time, urllib.request

CARD, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    b = urllib.request.urlopen(urllib.request.Request(
        u, headers={'User-Agent': UA}), timeout=30).read()
    time.sleep(1.2)
    try:
        return b.decode('euc_jp')
    except Exception:
        return b.decode('utf-8', 'replace')


def order(s):
    """'7-6,9-(12,1,13),4' → 先頭から並べた馬番の列"""
    return [int(x) for x in re.findall(r'\d+', s)]


C = json.load(open(CARD, encoding='utf-8'))
out = {}
for R in sorted(C, key=int):
    p = get(f"https://keiba.rakuten.co.jp/race_performance/list/RACEID/{C[R]['rid']}")
    t = re.sub(r'<[^>]+>', '\n', p).replace('&nbsp;', ' ')
    L = [x.strip() for x in t.split('\n') if x.strip()]
    d = dict(dist=C[R]['dist'])
    i = next((i for i, x in enumerate(L) if x == 'ハロンタイム'), None)
    if i is not None:
        lap = re.findall(r'\d{1,2}\.\d', L[i + 1]) if i + 1 < len(L) else []
        d['lap'] = [float(x) for x in lap]
        seg = ' '.join(L[i:i + 6])
        m4 = re.search(r'4F\s*([\d.]+)', seg)
        m3 = re.search(r'3F\s*([\d.]+)', seg)
        d['ag4'] = float(m4.group(1)) if m4 else None
        d['ag3'] = float(m3.group(1)) if m3 else None
    j = next((j for j, x in enumerate(L) if 'コーナー通過順位' in x), None)
    if j is not None:
        seg = L[j:j + 14]   # 1600m以上は1角〜4角の4つが並ぶ
        for k, lab in (('３角', 'c3'), ('４角', 'c4')):
            n = next((n for n, x in enumerate(seg) if x == k), None)
            if n is not None and n + 1 < len(seg):
                d[lab] = order(seg[n + 1])
                d[lab + 's'] = seg[n + 1]
    lp = d.get('lap') or []
    if len(lp) >= 6 and d.get('ag3'):
        d['f3'] = round(sum(lp[:3]), 1)
        d['lap33'] = round(sum(lp[-6:-3]) - d['ag3'], 1)   # 残り6〜3F − 上り3F
    out[R] = d
    print(f"{R:>3}R {d['dist']:>5}m  {'-'.join(f'{x:.1f}' for x in lp)}"
          f"  前3F {d.get('f3')}  上り3F {d.get('ag3')}  33ラップ {d.get('lap33')}",
          flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('書き出し', OUT)
