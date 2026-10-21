# -*- coding: utf-8 -*-
"""吉馬 地方競馬版から1日ぶんの競走成績を取る（楽天がメンテ中のときの代替）。

  python3 scripts/fetch_kichiuma.py 2026/10/21 18 out.json

ハロンタイムとコーナーの内外（通し位置）はこのサイトには無い。
取れるのは 着順・枠・馬番・馬名・性齢・斤量・騎手・馬体重・走破時計・着差・
上り3Fとその順位・4つのコーナー通過順・人気。
"""
import json, re, sys, time, urllib.parse, subprocess

DATE, PLACE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BASE = 'https://www.kichiuma-chiho.net/php/search.php'
UA = 'Mozilla/5.0'


def get(url):
    for i in range(4):
        p = subprocess.run(['curl', '-s', '-m', '30', '-H', 'User-Agent: ' + UA, url],
                           capture_output=True)
        if p.returncode == 0 and len(p.stdout) > 2000:
            return p.stdout.decode('utf-8', 'ignore')
        time.sleep(2 * (i + 1))
    return None


def cells(tr):
    return [re.sub(r'<[^>]+>', '', x).replace('&nbsp;', ' ').strip()
            for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]


def tsec(t):
    """'2:07:5' → '2:07.5'、'54:8' → '54.8'。"""
    t = t.strip()
    m = re.match(r'^(\d+):(\d\d):(\d)$', t)
    if m:
        return '%s:%s.%s' % m.groups()
    m = re.match(r'^(\d\d):(\d)$', t)
    if m:
        return '%s.%s' % m.groups()
    return t


out = {}
for R in range(1, 13):
    q = {'race_id': '%s%02d%s' % (DATE.replace('/', ''), R, PLACE),
         'date': DATE, 'no': str(R), 'id': PLACE, 'p': 'res'}
    raw = get(BASE + '?' + urllib.parse.urlencode(q))
    if raw is None:
        print('%2dR 取得NG' % R)
        continue
    i = raw.find('■競走成績')
    if i < 0:
        print('%2dR 成績なし' % R)
        continue
    seg = raw[i:i + 40000]
    txt = re.sub(r'<[^>]+>', ' ', raw[max(0, i - 4000):i])
    dm = re.search(r'ダート([\d,]+)m', txt)
    bm = re.search(r'馬場状態：([良稍重不]+)', txt)
    wm = re.search(r'天候：(\S+)', txt)
    nm = re.search(r'頭数：(\d+)頭', txt)
    cm = re.search(r'\s([^\s]{4,60})\s+サラブレッド系', txt)
    es = []
    for tr in re.split(r'<tr[^>]*>', seg):
        c = cells(tr)
        if len(c) < 16 or not c[0].isdigit() or not c[2].isdigit():
            continue
        if not c[6].endswith('kg') or not re.match(r'^(\d+-)+\d+$', c[14]):
            continue
        w = re.match(r'^(\d+)\(([-+]?\d+)\)$', c[9])
        sa = re.match(r'^([牡牝セ])(\d+)$', c[5])
        es.append(dict(f=c[0], waku=int(c[1]), u=int(c[2]), nm=c[3], belong=c[4],
                       sx=sa.group(1) if sa else '', age=int(sa.group(2)) if sa else 0,
                       kin=float(c[6].replace('kg', '') or 0), jk=c[7], tr=c[8],
                       wt=int(w.group(1)) if w else None,
                       dw=(w.group(2) if w else None),
                       tm=tsec(c[10]), margin=c[11],
                       ag=float(c[12]) if c[12] else None,
                       agr=int(c[13]) if c[13].isdigit() else None,
                       cor=c[14], c4=int(c[14].split('-')[-1]) if c[14] else None,
                       pop=int(c[15]) if c[15].isdigit() else None))
    if not es:
        print('%2dR 行が取れない' % R)
        continue
    out[str(R)] = dict(rid='%s%s%02d' % (DATE.replace('/', ''), PLACE, R),
                       dist=int(dm.group(1).replace(',', '')) if dm else 0,
                       baba=bm.group(1) if bm else '', weather=wm.group(1) if wm else '',
                       cls=(cm.group(1).strip() if cm else ''),
                       n=int(nm.group(1)) if nm else len(es), lap=None, e=es)
    print('%2dR ダ%-4d %s %2d頭 ／ 1着 %2d %-12s %2d人気 4角%s'
          % (R, out[str(R)]['dist'], out[str(R)]['baba'], len(es),
             es[0]['u'], es[0]['nm'][:12], es[0]['pop'], es[0]['c4']))
    time.sleep(1.0)
json.dump(out, open(OUT, 'w'), ensure_ascii=False)
print('→', OUT, len(out), '鞍')
