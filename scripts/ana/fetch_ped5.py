# -*- coding: utf-8 -*-
"""netkeiba の5代血統表を取る。母父より奥（母母父）とクロスを作るため。

  python3 scripts/ana/fetch_ped5.py <out.jsonl> [--days 2026-10-19,...] [--sleep 1.5]

吉馬から取れていたのは父・母・母父の3代まで。ここでは62セル（5代）を
そのまま持ってきて、母母父・母母母父・4代以内のクロスを作れる形にする。

- 馬名検索は EUC-JP でエンコードして渡す（UTF-8 だと「該当データなし」）
- 一意な馬名は馬ページへ転送されるので canonical から ID を取る
- 同名複数のときは生年と父で絞る
- 既に out.jsonl にある馬は飛ばす（中断しても続けられる）
"""
import json, glob, os, re, sys, time, urllib.request, urllib.parse, collections

ARG = sys.argv[1:]
OUT = ARG[0]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


SLEEP = float(opt('--sleep', 1.5))
DAYS = (opt('--days') or '').split(',') if opt('--days') else None
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}
TRACK = opt('--track', '浦和')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')

# 5代62セルの位置ラベル（文書順＝父から深さ優先）
SUB = {1: 31, 2: 15, 3: 7, 4: 3, 5: 1}


def labels():
    out = []

    def rec(path):
        out.append(path)
        if len(path) < 5:
            rec(path + '父')
            rec(path + '母')
    rec('父')
    rec('母')
    return out


LAB = labels()
assert len(LAB) == 62, len(LAB)


def get(u, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.Request(u, headers={'User-Agent': UA})
            return urllib.request.urlopen(r, timeout=30).read().decode('euc_jp', 'replace')
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 ** i * 2)


def clean(h):
    h = re.sub(r'<[^>]+>', '', h).replace('&nbsp;', ' ').replace('&amp;', '&')
    return re.sub(r'\s+', ' ', h).strip()


NAME = re.compile(r'^(.+?)\s*(?:\((?:[^)]*)\))?\s*(?:\d{4})?\s*(?:[^\s]*毛)?\s*(?:\[血統\]\[産駒\])?')


def cellname(c):
    """セルから馬名だけ抜く。'Galileo (愛) 1998 鹿毛 [血統][産駒] 9-h' → 'Galileo'"""
    c = re.sub(r'\[血統\]|\[産駒\]', ' ', c)
    c = re.sub(r'\b\d{4}\b.*$', '', c)          # 生年以降を落とす
    c = re.sub(r'\s*\((?:[^)]{1,6})\)\s*$', '', c.strip())
    c = re.sub(r'\s*\((?:米|英|愛|仏|独|加|豪|新|伊|日|南阿|亜|伯|智|UAE|香|印)\)', '', c)
    c = re.sub(r'\s+[\d]{1,2}-[a-z]\s*$', '', c)
    return c.strip()


def horse_id(nm, want_sire=None, want_year=None):
    q = urllib.parse.quote(nm.encode('euc_jp'))
    t = get(f'https://db.netkeiba.com/?pid=horse_list&word={q}')
    if '該当データが存在しません' in t:
        return None, 'なし'
    m = re.search(r'<link[^>]+rel="canonical"[^>]+href="[^"]*?/horse/(\d{10})/?"', t)
    if m:
        return m.group(1), 'canonical'
    cands = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S):
        i = re.search(r'/horse/(\d{10})/', r)
        if not i:
            continue
        cs = [clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
        if not cs or nm not in ' '.join(cs[:3]):
            continue
        cands.append((i.group(1), cs))
    if not cands:
        return None, '行なし'
    if want_year:
        f = [c for c in cands if any(str(want_year) in x for x in c[1][:4])]
        cands = f or cands
    if want_sire:
        f = [c for c in cands if any(want_sire in x for x in c[1])]
        cands = f or cands
    return cands[0][0], f'候補{len(cands)}'


def ped(hid):
    """62セルを {位置: [馬名, netkeiba ID]} で返す。IDは祖先グラフを伸ばすのに使う。"""
    t = get(f'https://db.netkeiba.com/horse/ped/{hid}/')
    m = re.search(r'blood_table.*?</table>', t, re.S)
    if not m:
        return None
    tds = re.findall(r'<td[^>]*>(.*?)</td>', m.group(0), re.S)
    if len(tds) != 62:
        return None
    out = {}
    for lab, td in zip(LAB, tds):
        i = re.search(r'/horse/(?:ped/)?([0-9a-z]{10})/?', td)
        out[lab] = [cellname(clean(td)), i.group(1) if i else None]
    return out


# ── 対象馬を集める ───────────────────────────────────────────
want = {}
for p in sorted(glob.glob('notes/live/*/results.json')):
    d = p.split('/')[2]
    if len(d) != 10 or (DAYS and d not in DAYS):
        continue
    for Rs, r in json.load(open(p, encoding='utf-8')).items():
        if BA.get(str(r.get('rid', ''))[8:10]) != TRACK:
            continue
        for e in r['e']:
            want.setdefault(e['nm'], e.get('age'))

have = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding='utf-8'):
        try:
            have.add(json.loads(l)['nm'])
        except Exception:
            pass

# 吉馬の3代血統（あれば同名の切り分けに使う）
y3 = {}
for p in ['/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/scratchpad/ped2026.jsonl']:
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            x = json.loads(l)
            y3[x['nm']] = x

todo = [n for n in want if n not in have]
print(f'対象 {len(want)}頭 / 済み {len(have)} / 取る {len(todo)}', flush=True)
f = open(OUT, 'a', encoding='utf-8')
ok = ng = mismatch = 0
for i, nm in enumerate(todo, 1):
    try:
        y = y3.get(nm)
        hid, how = horse_id(nm, y['sire'] if y else None,
                            (2026 - want[nm] if want.get(nm) else None))
        time.sleep(SLEEP)
        if not hid:
            ng += 1
            print(f'  NG {nm} ({how})', flush=True)
            continue
        pd = ped(hid)
        time.sleep(SLEEP)
        if not pd:
            ng += 1
            print(f'  NG {nm} 血統表なし {hid}', flush=True)
            continue
        bad = bool(y) and (pd['父'][0] != y['sire'] or pd['母'][0] != y['dam'])
        mismatch += bad
        f.write(json.dumps(dict(nm=nm, id=hid, how=how, chk=('NG' if bad else 'OK'),
                                p=pd), ensure_ascii=False) + '\n')
        f.flush()
        ok += 1
    except Exception as e:
        ng += 1
        print(f'  ERR {nm} {e}', flush=True)
    if i % 50 == 0:
        print(f'  {i}/{len(todo)}  OK{ok} NG{ng} 父母不一致{mismatch}', flush=True)
print(f'done OK{ok} NG{ng} 父母不一致{mismatch}', flush=True)
