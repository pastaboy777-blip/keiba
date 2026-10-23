# -*- coding: utf-8 -*-
"""吉馬の結果ページから血統（父・母・母父）を取る。

  python3 scripts/fetch_kichiuma_ped.py <日付と場のリスト.json> <出力.jsonl>
"""
import json, re, sys, time, urllib.parse, subprocess

SRC, OUT = sys.argv[1], sys.argv[2]
BASE = 'https://www.kichiuma-chiho.net/php/search.php'
BA = {'18': '浦和', '19': '船橋', '20': '大井', '21': '川崎'}


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


todo = json.load(open(SRC, encoding='utf-8'))
fo = open(OUT, 'a', encoding='utf-8')
n = 0
for k, (date, pid) in enumerate(todo):
    ymd = '%04d-%02d-%02d' % tuple(int(x) for x in date.split('/'))
    for R in range(1, 13):
        q = {'race_id': '%s%02d%s' % (''.join('%02d' % int(x) if j else x
                                              for j, x in enumerate(date.split('/'))), R, pid),
             'date': date, 'no': str(R), 'id': pid, 'p': 'res'}
        raw = get(BASE + '?' + urllib.parse.urlencode(q))
        time.sleep(1.1)
        if raw is None or '■血統' not in raw:
            continue
        i = raw.find('■血統')
        for c in [cells(tr) for tr in re.split(r'<tr[^>]*>', raw[i:i + 20000])]:
            if len(c) < 5 or not c[0].isdigit():
                continue
            fo.write(json.dumps(dict(d=ymd, ba=BA[pid], R=R, f=int(c[0]), nm=c[1],
                                     sire=c[2], dam=c[3], bms=c[4]), ensure_ascii=False) + '\n')
            n += 1
    fo.flush()
    print('[%d/%d] %s %s  ここまで %d頭' % (k + 1, len(todo), ymd, BA[pid], n), flush=True)
fo.close()
print('完了', n)
