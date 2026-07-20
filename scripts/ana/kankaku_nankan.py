"""南関 3歳下級戦「レース間隔別」成績＋危険パターン集計（中央の"夏の3歳未勝利"版）。
各出走馬の前走からの間隔(週)をDBページから計算→間隔バンド別に着別度数・勝率・連対・複勝・回収値。
危険パターン: ①押せ押せ(間隔≤2週の連戦×惜敗続き) ②休み明け(≥10週/半年で人気)。
※要cookie(kb.conf)。南関3歳下級戦のrid群を渡して実行。DAYS/場は用途に応じ設定。
"""
import re, os, sys
from collections import defaultdict
import monogatari as M
import hidden as H  # parse_db_races(cd) を再利用

# (head, mmdd, 場名) 南関7月の3歳下級戦を含む開催。cookie復帰後に拡張。
MEETS = {
 "大井": [("2026101003","0701"),("2026101004","0702"),("2026101005","0703"),
          ("2026111001","0720")],
 # 川崎(11)/船橋(12)/浦和(13) は nittei から rid 収集して追加
}
WEEK = 7  # 日→週

def target_date(mmdd):
    return (2026, int(mmdd[:2]), int(mmdd[2:]))

def days_between(a, b):
    import datetime
    return (datetime.date(*a) - datetime.date(*b)).days

def band(w):
    if w is None: return "初出走他"
    if w <= 1.2: return "連闘"
    if w <= 2.5: return "2週"
    if w <= 3.5: return "3週"
    if w <= 4.5: return "4週"
    if w <= 9.5: return "5〜9週"
    if w <= 25: return "10〜25週"
    return "半年以上"

def is_3sai_kakyu(title):
    return ("3歳" in title or "３歳" in title) and ("以上" not in title)

def race(rid):
    f = os.path.join(M.ARC, f"sei_{rid}.html")
    M._get(f"{M.BASE}/chihou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
    md = re.search(r"発走\s*[\d:]+\s*(.*?)\s*(\d{3,4})m", t)
    title = md.group(1).strip() if md else ""
    runners = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        row = m.group(1)
        if 'class="umaban"' not in row: continue
        tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 14 or not re.match(r"^\d+$", tds[0]): continue
        cd = re.search(r"/db/uma/(\d+)", row)
        ni = None
        for i in range(13, len(tds)-1):
            if re.match(r"^\d{1,2}$", tds[i]) and re.match(r"^\d{2}\.\d$", tds[i-1]) and re.match(r"^\d{1,3}\.\d$", tds[i+1]): ni=i;break
        runners.append({"chaku": int(tds[0]), "cd": cd.group(1) if cd else None,
                        "nk": int(tds[ni]) if ni else None})
    return title, runners

def run(tracks):
    tab = defaultdict(lambda: {"n":0,"win":0,"ren":0,"fuku":0,"tanpay":0,"fukupay":0})
    nr = 0
    for tname in tracks:
        for head, mmdd in MEETS.get(tname, []):
            td = target_date(mmdd)
            for rr in range(1, 13):
                rid = f"{head}{rr:02d}{mmdd}"
                try: title, runners = race(rid)
                except Exception: continue
                if not is_3sai_kakyu(title): continue
                nr += 1
                for r in runners:
                    w = None
                    if r["cd"]:
                        try:
                            races = sorted(H.parse_db_races(r["cd"]), key=lambda x:(x[0],x[1],x[2]), reverse=True)
                            prev = [x for x in races if (x[0],x[1],x[2]) < td]
                            if prev: w = days_between(td,(prev[0][0],prev[0][1],prev[0][2]))/WEEK
                        except Exception: pass
                    b = band(w); s = tab[b]; s["n"] += 1
                    if r["chaku"]==1: s["win"]+=1
                    if r["chaku"]<=2: s["ren"]+=1
                    if r["chaku"]<=3: s["fuku"]+=1
    order = ["連闘","2週","3週","4週","5〜9週","10〜25週","半年以上","初出走他"]
    print(f"=== 南関 3歳下級戦 間隔別成績（{nr}R・{'/'.join(tracks)}） ===")
    print(f"{'間隔':<8}{'頭数':>5}{'勝率':>7}{'連対':>7}{'複勝':>7}")
    for b in order:
        s = tab[b]
        if s["n"]:
            print(f"{b:<8}{s['n']:>5}{s['win']/s['n']*100:>6.1f}%{s['ren']/s['n']*100:>6.1f}%{s['fuku']/s['n']*100:>6.1f}%")

if __name__ == "__main__":
    run(sys.argv[1:] or ["大井"])
