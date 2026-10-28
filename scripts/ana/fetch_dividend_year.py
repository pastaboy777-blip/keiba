# -*- coding: utf-8 -*-
"""払戻金を1年ぶん取る。

  python3 scripts/ana/fetch_dividend_year.py <divdays.json> <out.json>

/race_dividend/list/RACEID/{18桁} はその日その場の全レースが1ページなので、
1日につき1回で足りる。取得済みの日は飛ばす。1.3秒あけて叩く。
"""
import json, os, re, sys, time, urllib.request

DAYS, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
KIND = ('単勝', '複勝', '枠複', '枠単', '馬複', 'ワイド', '馬単', '三連複', '三連単')
MULTI = ('複勝', 'ワイド')


def parse(p):
    """fetch_dividend.py と同じ読み方。買い目は数字とハイフンだけ、
    金額は末尾が「円」の行だけを拾う（この2つを混ぜると空になる）。"""
    t = re.sub(r'<[^>]+>', '\n', p).replace('&nbsp;', ' ')
    L = [x.strip() for x in t.split('\n') if x.strip()]
    heads = [(i, x) for i, x in enumerate(L) if re.match(r'^\d+R\s', x)]
    out = {}
    for k, (i, title) in enumerate(heads):
        j = heads[k + 1][0] if k + 1 < len(heads) else len(L)
        seg = L[i:j]
        d = {}
        pos = [(n, x) for n, x in enumerate(seg) if x in KIND]
        for n, (idx, kind) in enumerate(pos):
            end = pos[n + 1][0] if n + 1 < len(pos) else len(seg)
            body = seg[idx + 1:end]
            buys = [x for x in body if re.match(r'^[\d]+(-[\d]+)*$', x)]
            yens = [int(x[:-1].replace(',', '').strip())
                    for x in body if re.match(r'^[\d,]+\s*円$', x)]
            if buys and yens and kind not in d:
                d[kind] = list(zip(buys, yens))
        out[re.match(r'^(\d+)R', title).group(1)] = d
    return out


days = json.load(open(DAYS, encoding='utf-8'))
res = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
todo = [(y, r) for y, r in sorted(days.items()) if y not in res]
print(f'{len(days)}日 / 取得済み {len(res)} / これから {len(todo)}', flush=True)
for n, (ymd, rid) in enumerate(todo, 1):
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            f'https://keiba.rakuten.co.jp/race_dividend/list/RACEID/{rid}',
            headers={'User-Agent': UA}), timeout=30).read()
        try:
            p = b.decode('euc_jp')
        except Exception:
            p = b.decode('utf-8', 'replace')
        res[ymd] = parse(p)
        json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception as e:
        print(f'  {ymd} 取れず {e}', flush=True)
    time.sleep(1.3)
    if n % 20 == 0:
        print(f'  {n}/{len(todo)}', flush=True)
print(f'完了 {len(res)}日', flush=True)
