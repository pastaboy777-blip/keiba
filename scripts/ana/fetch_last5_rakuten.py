# -*- coding: utf-8 -*-
"""ある開催に出走した馬の、全場ぶんの出走履歴を取る。

  python3 scripts/ana/fetch_last5_rakuten.py <YYYYMMDD,...> <out.jsonl>

楽天の出馬表から馬のIDを拾い、1頭ずつ馬のページを読む。
馬のページの出走履歴は、場をまたいで1行ずつ並んでいる。

  日付 / 競馬場 / R / レース名 / 距離 / 馬場 / 天候 / 馬番 / 人気 /
  着順（着/頭数）/ タイム / 差 / 上3F / 馬体重 / 騎手 / 斤量 / 調教師

レース名が2行に割れる馬がいるので、列の数では数えず
「ダ1600」のような距離を目印にして前後に広げる。
取得済みの馬は飛ばすので、止めても続きから走る。1.2秒あける。
"""
import json, os, re, sys, time, urllib.request

DAYS, OUT = sys.argv[1].split(','), sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
BASE = 'https://keiba.rakuten.co.jp'
DIST = re.compile(r'^[ダ芝][\d,]{3,5}$')
DATE = re.compile(r'^\d{4}/\d{2}/\d{2}$')
SKIP = ('[', ']', '過去映像')


def get(u):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                u, headers={'User-Agent': UA}), timeout=30).read()
            time.sleep(1.2)
            for enc in ('utf-8', 'euc_jp', 'cp932'):
                try:
                    return b.decode(enc)
                except Exception:
                    pass
            return b.decode('utf-8', 'replace')
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def lines(p):
    t = re.sub(r'<[^>]+>', '\n', p).replace('&nbsp;', ' ')
    return [x.strip() for x in t.split('\n') if x.strip()]


def history(L):
    """出走履歴を1走ずつ取り出す"""
    out = []
    for d, x in enumerate(L):
        if not DATE.match(x):
            continue
        di = next((k for k in range(d + 3, min(d + 12, len(L)))
                   if DIST.match(L[k])), None)
        if di is None or di + 12 >= len(L):
            continue                       # 生年月日などの行
        nm = ' '.join(y for y in L[d + 3:di] if y not in SKIP)
        g = lambda k: L[di + k]
        out.append(dict(d=x, ba=L[d + 1], R=L[d + 2], race=nm, dist=L[di],
                        baba=g(1), tenki=g(2), u=g(3), pop=g(4), f=g(5),
                        tm=g(6), mgn=g(7), ag=g(8), wt=g(9), jk=g(10),
                        kin=g(11), tr=g(12)))
    return out


# ── 1) 出馬表から 馬名 → 馬のID ───────────────────────────
ids = {}
for ymd in DAYS:
    for R in range(1, 13):
        p = get(f'{BASE}/race_card/list/RACEID/{ymd}20151103{R:02d}')
        if not p:
            continue
        for hid, nm in re.findall(
                r'horse_detail/detail/HORSEID/(\d+)"[^>]*>([^<]+)<', p):
            nm = nm.strip()
            if nm and not nm.isdigit():
                ids.setdefault(nm, hid)
    print(f'  {ymd} まで {len(ids)}頭', flush=True)
print(f'馬のIDが取れたのは {len(ids)}頭', flush=True)

# ── 2) 1頭ずつ出走履歴 ────────────────────────────────
done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            done.add(json.loads(l)['nm'])
        except Exception:
            pass
todo = [(nm, hid) for nm, hid in sorted(ids.items()) if nm not in done]
print(f'取得済み {len(done)} / これから {len(todo)}', flush=True)

f = open(OUT, 'a', encoding='utf-8', buffering=1)
for n, (nm, hid) in enumerate(todo, 1):
    p = get(f'{BASE}/horse_detail/detail/HORSEID/{hid}')
    if not p:
        continue
    L = lines(p)
    rec = {'nm': nm, 'hid': hid}
    for k, lab in (('父馬：', 'sire'), ('母馬：', 'dam'), ('母父馬：', 'bms')):
        v = next((x[len(k):] for x in L[:120] if x.startswith(k)), '')
        if v:
            rec[lab] = v
    i = next((i for i, x in enumerate(L) if x == '調教師名'), None)
    if i is not None and i + 1 < len(L):
        rec['tr'] = L[i + 1]
    i = next((i for i, x in enumerate(L) if x == '生年月日'), None)
    if i is not None and i + 1 < len(L):
        rec['born'] = L[i + 1]
    h = history(L)
    rec['n'] = len(h)
    rec['runs'] = h[:8]
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 25 == 0:
        print(f'  {n}/{len(todo)}', flush=True)
print('完了', flush=True)
