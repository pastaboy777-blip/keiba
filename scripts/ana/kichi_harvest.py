
"""浦和 2026年ぶんを吉馬の結果ページから集める（過去走ランクWの穴作戦を測るため）。
  python3 urawa_year.py
出力: urawa_year.json  {race_id: {date,R,dist,n,tenko,baba,rows:[...]}}
各馬: 過去走ランク/前走ランク/各指数の順位/人気/着順/単勝・複勝配当。
"""
import re, json, os, time, datetime, urllib.request, urllib.parse

S = '/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/'
OUT = S + 'urawa_year.json'
BASE = 'https://www.kichiuma-chiho.net/php/search.php'
VID = '18'                      # 浦和
D0, D1 = datetime.date(2026, 1, 1), datetime.date(2026, 10, 21)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode('utf-8', 'replace')


def cells(tr):
    return [re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', c))
            for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]


def num(v, f=int):
    try:
        return f(v)
    except Exception:
        return None


def payouts(t):
    """単勝・複勝の配当を {馬番: 円} で返す"""
    tan, fuku = {}, {}
    m = re.search(r'単勝\s*(\d+)\s*([\d,]+)円', t)
    if m:
        tan[int(m.group(1))] = int(m.group(2).replace(',', ''))
    i = t.find('複勝')
    if i >= 0:
        seg = t[i:i + 300]
        # 少頭数だと枠連が無い。複勝の次に来る券種はどれでも切れるようにしないと
        # 「馬連複 5-8 770円」を 8番の複勝770円として拾ってしまう
        for kw in ('枠連', '馬連', 'ワイド', '馬単', '３連', '3連', '三連'):
            seg = seg.split(kw)[0]
        for ub, yen in re.findall(r'(\d+)\s+([\d,]+)円', seg)[:3]:
            fuku[int(ub)] = int(yen.replace(',', ''))
    return tan, fuku


def parse(h):
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
    if '開催データが存在しません' in t:
        return None
    md = re.search(r'ダート(\d+)m', t)
    mw = re.search(r'天候：(\S+?)\s*馬場状態：(\S+?)\s*頭数：(\d+)頭', t)
    tan, fuku = payouts(t)
    rec = {'dist': num(md.group(1)) if md else None,
           'tenko': mw.group(1) if mw else None, 'baba': mw.group(2) if mw else None,
           'n': num(mw.group(3)) if mw else None, 'rows': []}

    seiseki = {}
    i, j = h.find('競走成績'), h.find('指標一覧')
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', h[i:j], re.S):
        c = cells(tr)
        if len(c) < 16 or not re.match(r'^\d+$', c[0]):
            continue
        ag = re.match(r'^([\d.]+)$', c[12])
        seiseki[int(c[2])] = {'chaku': int(c[0]), 'jk': c[7], 'wt': c[9],
                              'agari': num(ag.group(1), float) if ag else None,
                              'agr': num(c[13]), 'tsuka': c[14], 'nk': num(c[15])}

    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', h[j:], re.S):
        c = cells(tr)
        if len(c) < 25 or not re.match(r'^\d+$', c[0]):
            continue
        ub = int(c[2])
        d = {'ub': ub, 'name': c[8], 'hyoka': c[3],
             'sp': num(c[4], float), 'sp_r': num(c[5]),
             'zenso_rank': c[6], 'kako_rank': c[7],
             'senko_r': num(c[11]), 'shinrai_r': num(c[14]),
             'chosei_r': num(c[17]), 'spmax_r': num(c[20]), 'sue_r': num(c[23]),
             'tan': tan.get(ub), 'fuku': fuku.get(ub)}
        d.update(seiseki.get(ub, {}))
        rec['rows'].append(d)
    return rec if rec['rows'] else None


store = json.load(open(OUT)) if os.path.exists(OUT) else {}
# 開催日はバックナンバー(/php/baknbr.php)から抜いたもの。日付はゼロ埋めなし形式
DATES = [l.strip() for l in open(S + 'urawa_dates.txt') if l.strip()]
days = 0
for ds in DATES:
    y, m, dd = (int(v) for v in ds.split('/'))
    key = '%04d%02d%02d' % (y, m, dd)
    if sum(1 for k in store if k.startswith(key)) >= 10:
        days += 1; continue
    try:
        idx = get(BASE + '?date=' + urllib.parse.quote(ds, safe='') + '&id=' + VID)
    except Exception as e:
        print('NG idx', ds, e, flush=True); continue
    rids = sorted(set(re.findall(r'race_id=(\d+)', idx)))
    rids = [r for r in rids if r.startswith(key)]
    days += 1
    got = 0
    for rid in rids:
        R = int(rid[8:10])
        url = (BASE + '?race_id=' + rid + '&date=' + urllib.parse.quote(ds, safe='')
               + '&no=%d&id=%s&p=res' % (R, VID))
        try:
            rec = parse(get(url))
        except Exception:
            rec = None
        if rec:
            rec.update(date=ds, R=R)
            store[rid] = rec; got += 1
        time.sleep(0.25)
    print('%-11s %2d鞍  （%d/%d日 累計%d鞍）' % (ds, got, days, len(DATES), len(store)), flush=True)
    json.dump(store, open(OUT, 'w'), ensure_ascii=False)
json.dump(store, open(OUT, 'w'), ensure_ascii=False)
print('DONE', days, '日', len(store), '鞍')
