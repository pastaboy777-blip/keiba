# -*- coding: utf-8 -*-
"""出走メンバーの全成績を取る。距離・流れ（前半-後半）・上り3F・通過順・馬体重。

  python3 scripts/ana/field_runs.py <field.json> <out.json> [--sleep 2]

netkeiba の馬ページは競走成績がJS描画で入っていないが、
/horse/result/<id>/ には表で載っている。
"""
import json, re, sys, time, urllib.request

ARG = sys.argv[1:]
FIELD, OUT = ARG[0], ARG[1]
SLEEP = float(ARG[ARG.index('--sleep') + 1]) if '--sleep' in ARG else 2.0
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def clean(h):
    h = re.sub(r'<[^>]+>', '', h).replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', h).strip()


def runs(hid):
    b = urllib.request.urlopen(urllib.request.Request(
        f'https://db.netkeiba.com/horse/result/{hid}/',
        headers={'User-Agent': UA}), timeout=30).read().decode('euc_jp', 'replace')
    m = re.search(r'<table[^>]*>.*?</table>', b, re.S)
    if not m:
        return []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', m.group(0), re.S)
    hdr = [clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', rows[0], re.S)]
    ix = {h: i for i, h in enumerate(hdr)}
    out = []
    for r in rows[1:]:
        cs = [clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
        if len(cs) < len(hdr) - 2:
            continue

        def g(k):
            return cs[ix[k]] if k in ix and ix[k] < len(cs) else ''
        out.append(dict(d=g('日付'), kai=g('開催'), race=g('レース名'), n=g('頭数'),
                        pop=g('人気'), f=g('着順'), jk=g('騎手'), kin=g('斤量'),
                        dist=g('距離'), baba=g('馬場'), tm=g('タイム'), mgn=g('着差'),
                        c=g('通過'), pace=g('ペース'), ag=g('上り'), wt=g('馬体重')))
    return out


field = json.load(open(FIELD, encoding='utf-8'))
res = {}
for h in field:
    try:
        res[h['nm']] = dict(id=h['id'], u=h.get('u'), runs=runs(h['id']))
        print(f"{h.get('u','')} {h['nm']} {len(res[h['nm']]['runs'])}走", flush=True)
    except Exception as e:
        print(f"  NG {h['nm']} {e}", flush=True)
    time.sleep(SLEEP)
json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('書き出し', OUT)
