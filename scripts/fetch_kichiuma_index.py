# -*- coding: utf-8 -*-
"""吉馬 地方競馬版から、競走成績とスピード指数（指標一覧）をまとめて取る。

  python3 scripts/fetch_kichiuma_index.py <日付と場のリスト.json> <出力.jsonl> [開始行]

リストは [["2026/10/21","18"], ...]。1行1頭でjsonlに追記する。
結果ページ1枚に着順と指標の両方が載っているので、1鞍あたり1リクエストで済む。
"""
import json, os, re, sys, time, urllib.parse, subprocess

SRC, OUT = sys.argv[1], sys.argv[2]
START = int(sys.argv[3]) if len(sys.argv) > 3 else 0
BASE = 'https://www.kichiuma-chiho.net/php/search.php'
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}
SLEEP = 1.1


def get(url):
    for i in range(3):
        p = subprocess.run(['curl', '-s', '-m', '30', '-H', 'User-Agent: Mozilla/5.0', url],
                           capture_output=True)
        if p.returncode == 0 and len(p.stdout) > 1500:
            return p.stdout.decode('utf-8', 'ignore')
        time.sleep(3 * (i + 1))
    return None


def cells(tr):
    return [re.sub(r'<[^>]+>', '', x).replace('&nbsp;', ' ').strip()
            for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]


def rows_after(raw, marker, span=40000):
    i = raw.find(marker)
    if i < 0:
        return []
    return [cells(tr) for tr in re.split(r'<tr[^>]*>', raw[i:i + span])]


def tsec(t):
    m = re.match(r'^(\d+):(\d\d):(\d)$', t)
    if m:
        return '%s:%s.%s' % m.groups()
    m = re.match(r'^(\d\d):(\d)$', t)
    if m:
        return '%s.%s' % m.groups()
    return t


def num(s):
    try:
        return float(s)
    except Exception:
        return None


def ival(s):
    return int(s) if s.isdigit() else None


todo = json.load(open(SRC, encoding='utf-8'))
fo = open(OUT, 'a', encoding='utf-8')
done = 0
for k, (date, pid) in enumerate(todo):
    if k < START:
        continue
    ymd = '%04d-%02d-%02d' % tuple(int(x) for x in date.split('/'))
    for R in range(1, 13):
        q = {'race_id': '%s%02d%s' % (''.join('%02d' % int(x) if j else x
                                              for j, x in enumerate(date.split('/'))), R, pid),
             'date': date, 'no': str(R), 'id': pid, 'p': 'res'}
        raw = get(BASE + '?' + urllib.parse.urlencode(q))
        time.sleep(SLEEP)
        if raw is None or '■競走成績' not in raw:
            continue
        head = re.sub(r'<[^>]+>', ' ', raw[:raw.find('■競走成績')])
        dm = re.search(r'ダート([\d,]+)m', head)
        bm = re.search(r'馬場状態：([良稍重不]+)', head)
        nm = re.search(r'頭数：(\d+)頭', head)
        res = {}
        for c in rows_after(raw, '■競走成績'):
            if len(c) < 16 or not c[0].isdigit() or not c[2].isdigit():
                continue
            if not c[6].endswith('kg') or not re.match(r'^(\d+-)+\d+$', c[14]):
                continue
            w = re.match(r'^(\d+)\(([-+]?\d+)\)$', c[9])
            res[int(c[2])] = dict(f=int(c[0]), waku=int(c[1]), u=int(c[2]), nm=c[3],
                                  belong=c[4], sx=c[5][:1], kin=num(c[6].replace('kg', '')),
                                  jk=c[7], tr=c[8],
                                  wt=int(w.group(1)) if w else None,
                                  dw=(w.group(2) if w else None),
                                  tm=tsec(c[10]), margin=c[11], ag=num(c[12]),
                                  agr=ival(c[13]), cor=c[14],
                                  c4=int(c[14].split('-')[-1]),
                                  first=int(c[14].split('-')[0]), pop=ival(c[15]))
        idx = {}
        for c in rows_after(raw, '■指標一覧'):
            if len(c) < 25 or not c[0].isdigit() or not c[2].isdigit():
                continue
            idx[int(c[2])] = dict(sp=num(c[4]), spr=ival(c[5]), rank1=c[6], rank2=c[7],
                                  senko=num(c[10]), senkor=ival(c[11]),
                                  sinrai=num(c[13]), sinrair=ival(c[14]),
                                  chosei=num(c[16]), choseir=ival(c[17]),
                                  spmax=num(c[19]), spmaxr=ival(c[20]),
                                  sueashi=num(c[22]), sueashir=ival(c[23]))
        if not res:
            continue
        for u, e in res.items():
            e.update(d=ymd, ba=BA[pid], R=R,
                     dist=int(dm.group(1).replace(',', '')) if dm else 0,
                     baba=bm.group(1) if bm else '',
                     n=int(nm.group(1)) if nm else len(res))
            e.update(idx.get(u) or {})
            fo.write(json.dumps(e, ensure_ascii=False) + '\n')
        done += 1
    fo.flush()
    print('[%d/%d] %s %s  ここまで %d鞍' % (k + 1, len(todo), ymd, BA[pid], done), flush=True)
fo.close()
print('完了', done, '鞍')
