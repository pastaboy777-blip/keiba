# -*- coding: utf-8 -*-
"""楽天競馬の出馬表を1日ぶん取る。

  python3 scripts/ana/fetch_card_rakuten.py <一覧のRACEID18桁> <out.json>

出馬表には 枠・馬番・父馬・馬名・母馬・性齢・負担重量・騎手・連対時馬体重・
前5走の着順 が入っている。母父は入っていないので吉馬で足す。
"""
import json, re, sys, time, urllib.request

LIST_ID, OUT = sys.argv[1], sys.argv[2]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def get(u):
    b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}),
                               timeout=30).read()
    time.sleep(1.0)
    try:
        return b.decode('euc_jp')
    except Exception:
        return b.decode('utf-8', 'replace')


def clean(h):
    h = re.sub(r'<[^>]+>', '\n', h).replace('&nbsp;', ' ')
    return [x.strip() for x in h.split('\n') if x.strip()]


t = get(f'https://keiba.rakuten.co.jp/race_card/list/RACEID/{LIST_ID}')
ids = sorted({x for x in re.findall(r'RACEID/(\d{18})', t) if x[:10] == LIST_ID[:10]})
ids = [x for x in ids if x != LIST_ID]
print(f'{LIST_ID[:8]} 場{LIST_ID[8:10]}  {len(ids)}鞍', flush=True)

out = {}
for rid in ids:
    try:
        p = get(f'https://keiba.rakuten.co.jp/race_card/list/RACEID/{rid}')
        title = (re.findall(r'<title>([^<]*)', p) or [''])[0].strip()
        R = int(re.search(r'(\d+)R', title).group(1)) if re.search(r'(\d+)R', title) else None
        head = ' '.join(clean(p[:6000])[:80])
        # 距離は見出しに直接は出ないが、各馬の成績欄の見出しが
        # 「当該競馬場 1600m成績」の形で当日の距離を持っている
        flat = ' '.join(clean(p))
        dm = (re.search(r'当該競馬場\s*(\d{3,4})\s*m', flat)
              or re.search(r'(\d{3,4})\s*m\s*成績', flat)
              or re.search(r'(ダ|芝)\s*(\d{3,4})\s*m', flat))
        dist = int(dm.group(dm.lastindex)) if dm else None
        # 枠番は rowspan で、同じ枠の2頭目には枠番セルが無い。
        # 必ず入っている「性齢（牡3 など）」のセルを基準に読む。
        tb = re.search(r'<table.*?</table>', p, re.S)
        SX = re.compile(r'^(牡|牝|セ)\d')
        horses = []
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb.group(0), re.S) if tb else []:
            tds = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)
            cells = [clean(x) for x in tds]
            k = next((i for i, c in enumerate(cells)
                      if c and SX.match(c[0].replace(' ', ''))), None)
            if k is None or k < 2:
                continue
            blood = cells[k - 1]                       # 父馬 / 馬名 / 母馬 / …
            nums = [c[0] for c in cells[:k - 1] if c and c[0].isdigit()]
            if not nums:
                continue
            prof = cells[k]
            horses.append(dict(
                waku=int(nums[0]) if len(nums) > 1 else None,
                u=int(nums[-1]),
                sire=blood[0] if len(blood) > 0 else '',
                nm=blood[1] if len(blood) > 1 else '',
                dam=blood[2] if len(blood) > 2 else '',
                prof=' '.join(prof[:4]),
                wt=' '.join(cells[k + 1][:2]) if k + 1 < len(cells) else '',
                prev=' / '.join(cells[k + 3][:6]) if k + 3 < len(cells) else ''))
        out[str(R)] = dict(rid=rid, title=title, dist=dist, n=len(horses), e=horses)
        print(f'  {R:>2}R {dist}m {len(horses)}頭', flush=True)
    except Exception as e:
        print(f'  NG {rid} {e}', flush=True)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('書き出し', OUT)
