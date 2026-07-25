#!/usr/bin/env python3
"""WIN5(JRA)出目コレクタ。指定年の7-8月で、新潟を1鞍でも含むWIN5回の
5レース勝ち馬(馬番/人気/馬名/上がり)＋WIN5配当を集め、一覧と人気/馬番傾向を出す。
データ源: race.netkeiba.com/top/win5.html?date=YYYYMMDD (対象5race_id) + db.netkeiba 結果。
使い方: python3 scripts/win5_collect.py 2023 2024 2025
"""
import sys, os, re, ssl, json, time, urllib.request, datetime, hashlib
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, "src")
from bs4 import BeautifulSoup
from nankeiba.scraping import netkeiba as N

JRA = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CTX = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt")
CACHE = Path("data/cache_win5"); CACHE.mkdir(exist_ok=True)
WIN5 = "https://race.netkeiba.com/top/win5.html?date={d}"
RESULT = "https://db.netkeiba.com/race/{rid}/"
_last = [0.0]


def get(url, enc="utf-8"):
    key = CACHE / (hashlib.md5(url.encode()).hexdigest() + ".html")
    if key.exists():
        return key.read_text(enc, "ignore")
    wait = 1.2 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    raw = urllib.request.urlopen(req, timeout=25, context=CTX).read()
    html = raw.decode(enc, "ignore")
    key.write_text(html, enc)
    return html


def win5_races(d):
    """その日のWIN5対象5race_idと配当情報。5本無ければ([],{})。"""
    try:
        h = get(WIN5.format(d=d))
    except Exception:
        return [], {}
    rids = sorted(set(re.findall(r"race_id=(\d{12})", h)))
    rids = [r for r in rids if r[:8] == d[:4] + r[4:8][:0] + d[4:] or True]  # 年一致は緩く
    rids = sorted(set(re.findall(r"race_id=(\d{12})", h)))
    if len(rids) != 5:
        return [], {}
    pay = {}
    txt = BeautifulSoup(h, "html.parser").get_text(" ", strip=True)
    # 「払戻金 483万4060円」= 483*10000+4060 / 「払戻金 9730円」= 9730
    mp = re.search(r"払戻金[^\d]{0,6}(?:(\d+)万)?([\d,]+)\s*円", txt)
    if mp:
        man = int(mp.group(1)) if mp.group(1) else 0
        pay["payoff"] = man * 10000 + int(mp.group(2).replace(",", ""))
    else:
        pay["payoff"] = None
    mv = re.search(r"的中票数[^\d]{0,6}([\d,]+)\s*票", txt)
    pay["hit_votes"] = int(mv.group(1).replace(",", "")) if mv else None
    return rids, pay


def winner(rid):
    """結果から1着(馬番,人気,馬名,上がり,4角位置)。取れなければNone。"""
    try:
        rows = N.parse_result(get(RESULT.format(rid=rid), enc="euc-jp"))
    except Exception:
        return None
    if not rows:
        return None
    r0 = rows[0]
    return {"umaban": r0.get("umaban"), "pop": r0.get("popularity"),
            "name": r0.get("horse"), "agari": r0.get("agari"),
            "odds": r0.get("win_odds"), "field": len(rows)}


def collect(years):
    rounds = []
    for y in years:
        for mo in (7, 8):
            d = datetime.date(y, mo, 1)
            while d.month == mo:
                ds = d.strftime("%Y%m%d")
                rids, pay = win5_races(ds)
                if len(rids) == 5:
                    places = [JRA.get(r[4:6], "?") for r in rids]
                    if "新潟" in places:            # 新潟を1鞍でも含む回のみ
                        legs = []
                        for r in rids:
                            w = winner(r)
                            legs.append({"place": JRA.get(r[4:6], "?"), "R": int(r[10:12]),
                                         "rid": r, **(w or {})})
                        rounds.append({"date": ds, "payoff": pay.get("payoff"),
                                       "hit_votes": pay.get("hit_votes"), "legs": legs})
                        sys.stderr.write(f"  {ds} 新潟含むWIN5 5鞍取得\n"); sys.stderr.flush()
                d += datetime.timedelta(days=1)
    return rounds


def main():
    years = [int(x) for x in sys.argv[1:]] or [2023, 2024, 2025]
    rounds = collect(years)
    Path("scratchpad/win5_rounds.json").write_text(json.dumps(rounds, ensure_ascii=False, indent=1))
    print(f"=== WIN5出目(新潟含む回) {years} 7-8月 / {len(rounds)}回 ===\n")
    # 一覧
    for rd in rounds:
        po = f"{rd['payoff']:,}円" if rd["payoff"] else "配当?"
        print(f"■ {rd['date']}  WIN5配当 {po}")
        for lg in rd["legs"]:
            nige = ""
            mark = "◆新潟" if lg["place"] == "新潟" else ""
            print(f"   {lg['place']}{lg['R']:>2}R  {str(lg.get('umaban','?')):>2}番 "
                  f"{str(lg.get('pop','?')):>2}人気 {(lg.get('name') or '?')[:10]:10s} {mark}")
        print()
    # 傾向集計
    allpop = [lg.get("pop") for rd in rounds for lg in rd["legs"] if lg.get("pop")]
    niipop = [lg.get("pop") for rd in rounds for lg in rd["legs"] if lg.get("pop") and lg["place"] == "新潟"]
    allum = [lg.get("umaban") for rd in rounds for lg in rd["legs"] if lg.get("umaban")]
    niium = [lg.get("umaban") for rd in rounds for lg in rd["legs"] if lg.get("umaban") and lg["place"] == "新潟"]

    def dist(vals, label):
        n = len(vals)
        if not n:
            print(f" {label}: データ無"); return
        c = Counter(vals)
        print(f" {label} (n={n}) 平均{sum(vals)/n:.1f}")
        # 人気帯
        b = {"1人気": sum(1 for v in vals if v == 1), "2-3": sum(1 for v in vals if 2 <= v <= 3),
             "4-6": sum(1 for v in vals if 4 <= v <= 6), "7-9": sum(1 for v in vals if 7 <= v <= 9),
             "10+": sum(1 for v in vals if v >= 10)}
        print("   " + " / ".join(f"{k}:{v}({v/n:.0%})" for k, v in b.items()))
    print("=== 傾向集計 ===")
    dist(allpop, "全5鞍の勝ち馬人気")
    dist(niipop, "新潟レースの勝ち馬人気")
    print()
    def umdist(vals, label):
        n = len(vals)
        if not n:
            return
        inn = sum(1 for v in vals if v <= 4); mid = sum(1 for v in vals if 5 <= v <= 9); out = sum(1 for v in vals if v >= 10)
        print(f" {label}(n={n}) 内1-4:{inn}({inn/n:.0%}) 中5-9:{mid}({mid/n:.0%}) 外10+:{out}({out/n:.0%})")
    umdist(allum, "全5鞍 馬番")
    umdist(niium, "新潟   馬番")
    pays = [rd["payoff"] for rd in rounds if rd["payoff"]]
    if pays:
        pays.sort()
        print(f"\n WIN5配当: 中央値{pays[len(pays)//2]:,}円 最高{max(pays):,}円 最低{min(pays):,}円")


if __name__ == "__main__":
    main()
