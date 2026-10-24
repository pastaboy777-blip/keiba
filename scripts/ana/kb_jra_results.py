# -*- coding: utf-8 -*-
"""競馬ブック（中央）の成績を1日ぶん取る。芝・ダートを分けて見るため。

  python3 scripts/ana/kb_jra_results.py 20261024 <out.json>

netkeiba が 400 を返すようになったため、こちらを使う。
成績ページには 4角位置（内/中/外）・前半3F・上り3F・通過順位・ペース・決め手まで載る。
Cookie は環境変数 KEIBABOOK_COOKIE（scratchpad の .kbcookie3）。有料サイトなので
1.3秒間隔・1日36鞍までにとどめる。
"""
import json, os, re, sys, time, urllib.request
from bs4 import BeautifulSoup

DATE, OUT = sys.argv[1], sys.argv[2]
BASE = 'https://p.keibabook.co.jp'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
CK = os.environ['KEIBABOOK_COOKIE'].strip()


CACHE = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
         'scratchpad/kbcache')
os.makedirs(CACHE, exist_ok=True)


def get(p):
    """有料サイトなので、取った生HTMLはキャッシュして二度取らない。"""
    f = os.path.join(CACHE, p.strip('/').replace('/', '_') + '.html')
    if os.path.exists(f):
        return open(f, encoding='utf-8').read()
    r = urllib.request.Request(BASE + p, headers={'User-Agent': UA, 'Cookie': CK})
    b = urllib.request.urlopen(r, timeout=30).read().decode('utf-8', 'replace')
    open(f, 'w', encoding='utf-8').write(b)
    time.sleep(1.3)
    return b


nit = get(f'/cyuou/nittei/{DATE}')
ids = sorted(set(re.findall(r'/cyuou/seiseki/(\d{12})', nit)))
print(f'{DATE}  {len(ids)}鞍', flush=True)

out = {}
for rid in ids:
    try:
        t = get(f'/cyuou/seiseki/{rid}')
        s = BeautifulSoup(t, 'html.parser')
        hs = [h.get_text(' ', strip=True) for h in s.find_all(['h1', 'h2', 'h3'])]
        kai = next((h for h in hs if '回' in h and '日目' in h), '')
        ba = re.sub(r'^\d+回|\d+日目$', '', kai)
        name = next((h for h in hs if h and h != 'p.keibabook.co.jp' and h != kai), '')
        txt = s.get_text(' ', strip=True)
        # 「1400m (ダート・左) 小雨・良」の形で入っている
        m = re.search(r'(\d{3,4})m\s*[（(]\s*(芝|ダート)\s*・\s*([^)）]*)[)）]\s*'
                      r'([^\s・]+)・(良|稍重|重|不良)', txt)
        if m:
            dist, surf, turn, tenki, baba = (int(m.group(1)), m.group(2), m.group(3),
                                             m.group(4), m.group(5))
        else:
            m2 = re.search(r'(\d{3,4})m\s*[（(]\s*(芝|ダート)', txt)
            dist = int(m2.group(1)) if m2 else None
            surf = m2.group(2) if m2 else None
            turn = tenki = ''
            b2 = re.search(r'(良|稍重|重|不良)', txt)
            baba = b2.group(1) if b2 else ''
        pace = (re.search(r'ペース\s*(\S+)', txt) or [None, ''])[1] if re.search(r'ペース\s*(\S+)', txt) else ''
        kime = (re.search(r'決め手\s*([^\s].{0,40}?)\s*(?:馬装具|発走状況|通過タイム)', txt) or [None, ''])
        kime = kime[1] if not isinstance(kime, re.Match) else kime.group(1)
        agari = (re.search(r'上り\s*([\d.]+-[\d.]+)', txt) or [None, ''])
        agari = agari[1] if not isinstance(agari, re.Match) else agari.group(1)
        avg = (re.search(r'平均ハロン\s*([\d.]+)', txt) or [None, ''])
        avg = avg[1] if not isinstance(avg, re.Match) else avg.group(1)
        tsuka = re.search(r'通過タイム((?:\s*\d+m)+)((?:\s*[\d.:]+)+)', txt)
        tsuka = re.findall(r'[\d.:]+', tsuka.group(2))[:6] if tsuka else []
        lapm = re.search(r'ラップタイム((?:\s*\d+m)+)((?:\s*[\d.]+)+)', txt)
        lap = re.findall(r'\d{1,2}\.\d', lapm.group(2))[:14] if lapm else []
        # 行によって「My印」のセルが無く列がずれるので、
        # 必ず入っている「性齢」を基準に相対位置で読む
        rows = []
        SX = re.compile(r'^[牡牝セ]\d+$')
        for tb in s.find_all('table'):
            hd = ''.join(c.get_text('', strip=True) for c in tb.find_all('tr')[0].find_all(['th', 'td']))
            if '着順' not in hd:
                continue
            for tr in tb.find_all('tr')[1:]:
                cs = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
                k = next((i for i, v in enumerate(cs) if SX.match(v.replace(' ', ''))), None)
                if k is None or k < 3:
                    continue

                def at(j):
                    return cs[j] if 0 <= j < len(cs) else ''
                # 重量と騎手の間に「騎手印」のセルが1つ入る（空のことも多い）
                rows.append(dict(f=at(0), waku=at(k - 3), u=at(k - 2), nm=at(k - 1),
                                 sxage=at(k), kin=at(k + 1), jk=at(k + 3), tm=at(k + 4),
                                 mgn=at(k + 5), c=at(k + 6), lane=at(k + 7),
                                 f3=at(k + 8), ag=at(k + 9), pop=at(k + 10),
                                 odds=at(k + 11), wt=at(k + 12), dw=at(k + 13)))
            break
        out[rid] = dict(ba=ba, kai=kai, R=int(rid[-2:]), name=name, surf=surf, dist=dist,
                        baba=baba, turn=turn, tenki=tenki, pace=pace, kime=kime, agari=agari, avg=avg,
                        tsuka=tsuka, lap=lap, e=rows)
        print(f'  {ba}{out[rid]["R"]:>2}R {surf}{dist} {baba} {len(rows)}頭 {name[:16]}', flush=True)
    except Exception as e:
        print(f'  NG {rid} {e}', flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('書き出し', OUT, len(out), '鞍')
